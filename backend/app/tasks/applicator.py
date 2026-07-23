from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
import uuid as uuid_module
import secrets
from datetime import datetime


def _pick_sender_email(db, profile):
    """
    Pick the best email account for this profile to send the next email.
    Returns (sender_email, token_json) using round-robin across connected
    accounts that haven't hit the daily limit of 15 emails.
    Prefers the account with fewest emails sent today.
    """
    from app.models.profile import ProfileEmail
    from app.models.email_account import EmailAccount
    from app.models.application import Application, ApplicationStatus
    from app.models.settings import GlobalSetting
    from sqlalchemy import func
    from datetime import timedelta

    limit_row = db.query(GlobalSetting).filter(GlobalSetting.key == "daily_email_limit").first()
    DAILY_LIMIT = int(limit_row.value) if limit_row and limit_row.value else 15

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    candidates = []

    # All emails belonging to this profile — token may be on ProfileEmail or EmailAccount
    profile_emails = db.query(ProfileEmail).filter(
        ProfileEmail.profile_id == profile.id,
    ).all()
    for pe in profile_emails:
        token = pe.gmail_token
        if not token:
            ea = db.query(EmailAccount).filter(
                EmailAccount.email == pe.email,
                EmailAccount.is_authorized == True,
                EmailAccount.is_active == True,
            ).first()
            if ea:
                token = ea.gmail_token
        if not token:
            continue
        # Count by sent_at (actual send time), not scheduled_at, to correctly enforce
        # Gmail's daily sending limit regardless of when emails were scheduled.
        count = db.query(func.count(Application.id)).filter(
            Application.sender_email == pe.email,
            Application.sent_at >= today_start,
            Application.sent_at < today_end,
            Application.status.in_([
                ApplicationStatus.sent, ApplicationStatus.sending,
            ]),
        ).scalar() or 0
        if count < DAILY_LIMIT:
            candidates.append((pe.email, token, count))

    if not candidates:
        print(f"[Applicator] All email accounts at daily limit (15) for profile {profile.id}")
        return None, None

    # Pick account with fewest emails today
    candidates.sort(key=lambda x: x[2])
    best_email, best_token, _ = candidates[0]
    return best_email, best_token


@celery_app.task(name="app.tasks.applicator.apply_job_task")
def apply_job_task(job_id: str):
    from app.models.job import Job, JobContact, JobStatus
    from app.models.profile import Profile, ProfileSkill, ProfileCV, ProfileEmail, SkillType
    from app.models.email_template import EmailTemplate, TemplateType
    from app.models.application import Application, ApplicationStatus
    from app.models.settings import GlobalSetting
    from app.services.ai_service import generate_job_email, modify_cv_for_job
    from app.services.cv_service import extract_cv_text, prepare_cv_for_job
    from app.services.scheduler_service import get_send_datetime
    from app.core.config import settings as app_settings

    with SyncSessionLocal() as db:
        job = db.query(Job).filter(Job.id == uuid_module.UUID(job_id)).first()
        if not job or not job.matched_profile_id:
            return
        if job.auto_apply_enabled is False:
            print(f"[Applicator] Auto-apply disabled for job {job_id}, skipping")
            return

        contact = db.query(JobContact).filter(JobContact.job_id == job.id, JobContact.is_primary == True).first()
        if not contact or not contact.email:
            print(f"[Applicator] No contact email for job {job_id}, skipping")
            return

        profile = db.query(Profile).filter(Profile.id == job.matched_profile_id).first()
        if not profile:
            return

        # Don't apply to the same job twice (primary guard — DB also has unique index on job_id+profile_id)
        if job.id:
            existing_job = db.query(Application).filter(
                Application.profile_id == profile.id,
                Application.job_id == job.id,
            ).first()
            if existing_job:
                # Allow re-apply if previous application was bounced
                if existing_job.status == ApplicationStatus.bounced:
                    pass  # fall through and create a new application
                elif existing_job.status == ApplicationStatus.sent:
                    job.status = JobStatus.applied
                    db.commit()
                    print(f"[Applicator] Already applied to job {job.id}, synced job status to {job.status}")
                    return
                else:
                    job.status = JobStatus.scheduled
                    db.commit()
                    print(f"[Applicator] Already applied to job {job.id}, synced job status to {job.status}")
                    return

        # Don't email the same address twice from the same profile (secondary guard)
        # Exclude bounced/rejected/failed so a re-send after contact update goes through
        existing = db.query(Application).filter(
            Application.profile_id == profile.id,
            Application.to_email == contact.email,
            Application.status.notin_([
                ApplicationStatus.rejected,
                ApplicationStatus.failed,
                ApplicationStatus.bounced,
            ]),
        ).first()
        if existing:
            # This contact was already emailed for a different job — mark this one skipped
            job.status = JobStatus.skipped
            db.commit()
            print(f"[Applicator] Contact {contact.email} already reached by profile {profile.id}, marking job skipped")
            return

        # Lock the job immediately so a concurrent apply_job_task invocation sees it and exits
        job.status = JobStatus.scheduled
        db.commit()

        def _revert_to_ready(reason: str):
            job.status = JobStatus.ready
            db.commit()
            print(f"[Applicator] Reverted job {job_id} to ready: {reason}")

        # Pick best sender email (round-robin, respects daily limit)
        sender_email, sending_token_json = _pick_sender_email(db, profile)
        if not sending_token_json:
            _revert_to_ready("no Gmail token on any profile email account")
            return

        # Resolve ProfileEmail FK (may be None if using EmailAccount only)
        profile_email = db.query(ProfileEmail).filter(
            ProfileEmail.profile_id == profile.id,
            ProfileEmail.email == sender_email,
        ).first()

        # Map job country (full name or ISO code) → CV region tag
        _COUNTRY_TO_REGION = {
            # United States
            "united states": "US", "us": "US", "usa": "US",
            # Canada
            "canada": "CA", "ca": "CA",
            # United Kingdom
            "united kingdom": "UK", "uk": "UK", "gb": "UK", "great britain": "UK", "england": "UK",
            # Australia
            "australia": "AU", "au": "AU",
            # United Arab Emirates
            "united arab emirates": "AE", "uae": "AE", "ae": "AE",
            # India
            "india": "IN", "in": "IN",
            # Germany
            "germany": "DE", "de": "DE", "deutschland": "DE",
            # New Zealand
            "new zealand": "NZ", "nz": "NZ",
            # Singapore
            "singapore": "SG", "sg": "SG",
            # Pakistan
            "pakistan": "PK", "pk": "PK",
            # Ireland
            "ireland": "IE", "ie": "IE",
            # South Africa
            "south africa": "ZA", "za": "ZA",
            # Nigeria
            "nigeria": "NG", "ng": "NG",
            # Kenya
            "kenya": "KE", "ke": "KE",
            # France
            "france": "FR", "fr": "FR",
            # Netherlands
            "netherlands": "NL", "nl": "NL", "holland": "NL",
            # Sweden
            "sweden": "SE", "se": "SE",
            # Denmark
            "denmark": "DK", "dk": "DK",
            # Norway
            "norway": "NO", "no": "NO",
            # Finland
            "finland": "FI", "fi": "FI",
            # Italy
            "italy": "IT", "it": "IT",
            # Spain
            "spain": "ES", "es": "ES",
        }
        _raw_country = (job.country or "").strip().lower()
        _target_region = _COUNTRY_TO_REGION.get(_raw_country, "OTHER")

        # Try exact region match first, then OTHER, then any active (default/untagged)
        cv = db.query(ProfileCV).filter(
            ProfileCV.profile_id == profile.id,
            ProfileCV.is_active == True,
            ProfileCV.region == _target_region,
        ).order_by(ProfileCV.uploaded_at.desc()).first()
        if not cv and _target_region != "OTHER":
            cv = db.query(ProfileCV).filter(
                ProfileCV.profile_id == profile.id,
                ProfileCV.is_active == True,
                ProfileCV.region == "OTHER",
            ).order_by(ProfileCV.uploaded_at.desc()).first()
        if not cv:
            # Final fallback: any active CV (default/untagged)
            cv = db.query(ProfileCV).filter(
                ProfileCV.profile_id == profile.id,
                ProfileCV.is_active == True,
            ).order_by(ProfileCV.uploaded_at.desc()).first()
        if not cv:
            _revert_to_ready(f"no active CV for profile {profile.name}")
            try:
                from app.services.alert_service import create_alert
                from app.models.alert import AlertType, AlertSeverity
                create_alert(
                    type=AlertType.system_error,
                    severity=AlertSeverity.warning,
                    title=f"No CV found for profile {profile.name}",
                    message=f"Job '{job.title}' at {job.company_name} is ready but profile '{profile.name}' has no active CV. Upload a CV in Profiles to unblock.",
                    source="Applicator",
                )
            except Exception:
                pass
            return

        primary_skills = [
            s.skill for s in db.query(ProfileSkill).filter(
                ProfileSkill.profile_id == profile.id, ProfileSkill.skill_type == SkillType.primary
            ).all()
        ]

        template = db.query(EmailTemplate).filter(
            EmailTemplate.template_type == TemplateType.job_initial,
            EmailTemplate.is_active == True,
            EmailTemplate.is_default == True,
        ).first()

        template_subject = template.subject if template else "Application for {role} position"
        template_body = template.body if template else "Hi,\n\nI am interested in the {role} role.\n\nBest regards,\n{name}"

        email_content = generate_job_email(
            job_title=job.title,
            company_name=job.company_name or "",
            job_description=job.job_description or "",
            profile_name=profile.name,
            profile_skills=primary_skills,
            template_subject=template_subject,
            template_body=template_body,
            hiring_person_name=contact.name,
            profile_bio=profile.bio or "",
            years_experience=profile.years_experience,
        )

        cv_pdf_path = cv.file_path if cv else None
        tailor_setting = db.query(GlobalSetting).filter(GlobalSetting.key == "cv_tailoring_enabled").first()
        cv_tailoring_enabled = (tailor_setting.value == "true") if tailor_setting else False
        if cv and cv_tailoring_enabled:
            try:
                cv_text = extract_cv_text(cv.file_path)
                if cv_text.strip():
                    updated_cv_text = modify_cv_for_job(
                        cv_text, job.title,
                        job.job_description or "",
                        primary_skills,
                    )
                    # Save tailored CV to permanent storage so it persists and is serveable
                    from app.core.config import settings as _cfg
                    import os as _os
                    tailored_dir = _os.path.join(_cfg.STORAGE_PATH, "cvs", "tailored", str(profile.id))
                    _os.makedirs(tailored_dir, exist_ok=True)
                    output_path = _os.path.join(tailored_dir, f"{job.id}.pdf")
                    cv_pdf_path = prepare_cv_for_job(cv.file_path, updated_cv_text, output_path=output_path)
            except Exception as e:
                print(f"[Applicator] CV tailoring error: {e}")

        approval_setting = db.query(GlobalSetting).filter(GlobalSetting.key == "approval_enabled_jobs").first()
        approval_enabled = (approval_setting.value == "true") if approval_setting else True

        # Manual jobs: send immediately, bypass approval and send window
        is_manual = getattr(job, "uploaded_manually", False)
        if is_manual:
            scheduled_at = datetime.utcnow()
            final_status = ApplicationStatus.scheduled
        else:
            scheduled_at = get_send_datetime(job.country or "US", sender_email=sender_email)
            final_status = ApplicationStatus.pending_approval if approval_enabled else ApplicationStatus.scheduled

        tracking_id = secrets.token_hex(16)

        application = Application(
            job_id=job.id,
            profile_id=profile.id,
            profile_email_id=profile_email.id if profile_email else None,
            sender_email=sender_email,
            to_email=contact.email,
            to_name=contact.name,
            subject=email_content.get("subject", ""),
            body=email_content.get("body", ""),
            cv_path=cv_pdf_path,
            status=final_status,
            scheduled_at=scheduled_at,
            tracking_id=tracking_id,
        )
        db.add(application)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[Applicator] Application commit failed for job {job_id}: {e}")
            _revert_to_ready(f"application commit error: {e}")
            return

        if template:
            template.times_used += 1
            db.commit()

        # NOTE: Do NOT dispatch send_application_task here via apply_async(eta=...).
        # All sends go through send_scheduled_applications_task (runs every 5 min)
        # which picks ONE app per tick. This prevents Redis from queuing stale
        # eta tasks that burst-fire when the worker restarts after downtime.


@celery_app.task(name="app.tasks.applicator.send_application_task")
def send_application_task(application_id: str):
    from app.models.application import Application, ApplicationStatus, ApplicationFollowup
    from app.models.profile import ProfileEmail, Profile
    from app.models.job import Job, JobStatus
    from app.models.email_template import EmailTemplate, TemplateType
    from app.models.settings import GlobalSetting
    from app.services.gmail_service import send_email
    from app.services.ai_service import generate_followup_email
    from app.services.scheduler_service import get_followup_datetime
    import json

    with SyncSessionLocal() as db:
        # Use SELECT FOR UPDATE SKIP LOCKED — if another worker is already sending
        # this application, we skip immediately instead of sending a duplicate.
        app = db.query(Application).filter(
            Application.id == uuid_module.UUID(application_id),
            Application.sent_at.is_(None),
            Application.status.notin_([ApplicationStatus.sent, ApplicationStatus.failed]),
        ).with_for_update(skip_locked=True).first()
        if not app:
            print(f"[Applicator] Application {application_id} already sent/failed/locked, skipping")
            return

        # Always use same sender_email chosen at scheduling time
        sender_email = app.sender_email
        sending_token_json = None

        if sender_email:
            pe = db.query(ProfileEmail).filter(ProfileEmail.email == sender_email).first()
            if pe and pe.gmail_token:
                sending_token_json = pe.gmail_token

            if not sending_token_json:
                from app.models.email_account import EmailAccount
                ea = db.query(EmailAccount).filter(
                    EmailAccount.email == sender_email,
                    EmailAccount.is_authorized == True,
                ).first()
                if ea and ea.gmail_token:
                    sending_token_json = ea.gmail_token

        if not sending_token_json:
            print(f"[Applicator] No Gmail token for {sender_email} — application {application_id} marked failed")
            app.status = ApplicationStatus.failed
            db.commit()
            return

        try:
            _profile = db.query(Profile).filter(Profile.id == app.profile_id).first()
            _sender_name = _profile.name if _profile else None

            result_msg = send_email(
                token_json=sending_token_json,
                sender=sender_email,
                to=app.to_email,
                subject=app.subject,
                body=app.body,
                tracking_pixel_url=None,
                pdf_path=app.cv_path,
                sender_name=_sender_name,
            )
            app.status = ApplicationStatus.sent
            app.sent_at = datetime.utcnow()
            app.sender_email = sender_email
            app.gmail_message_id = result_msg.get("id")
            app.gmail_thread_id = result_msg.get("threadId")

            job_for_status = db.query(Job).filter(Job.id == app.job_id).first()
            if job_for_status:
                job_for_status.status = JobStatus.applied

        except Exception as e:
            print(f"[Applicator] Send error: {e}")
            app.status = ApplicationStatus.failed
            db.commit()
            try:
                from app.services.alert_service import create_alert
                from app.models.alert import AlertType, AlertSeverity
                err_str = str(e).lower()
                if any(w in err_str for w in ["invalid_grant", "token", "unauthorized", "credentials", "auth"]):
                    create_alert(
                        type=AlertType.email_disconnected,
                        severity=AlertSeverity.error,
                        title=f"Email account disconnected: {sender_email}",
                        message=f"Gmail token invalid or expired for {sender_email}. Please re-authorise the account in Email Accounts settings.\nError: {str(e)[:300]}",
                        source="Email Sender",
                    )
                else:
                    create_alert(
                        type=AlertType.email_error,
                        severity=AlertSeverity.error,
                        title=f"Failed to send email to {app.to_email}",
                        message=str(e)[:300],
                        source="Email Sender",
                    )
            except Exception:
                pass
            return

        # Commit the sent status BEFORE creating follow-ups so follow-ups are
        # only written if the email actually went out successfully.
        db.commit()

        # Dispatch follow-up scheduling as a SEPARATE task — decoupled from send so a
        # worker restart between send and follow-up creation doesn't lose follow-ups.
        schedule_followups_task.delay(application_id)


@celery_app.task(name="app.tasks.applicator.schedule_followups_task")
def schedule_followups_task(application_id: str):
    """
    Create pending follow-up records for a successfully sent application.
    Runs as a separate task so worker restarts can't lose follow-ups.
    Idempotent — safe to re-run; skips follow-up numbers already created.
    """
    from app.models.application import Application, ApplicationStatus, ApplicationFollowup
    from app.models.profile import Profile
    from app.models.job import Job
    from app.models.email_template import EmailTemplate, TemplateType
    from app.models.settings import GlobalSetting
    from app.services.ai_service import generate_followup_email
    from app.services.scheduler_service import get_followup_datetime
    import json, redis as _redis
    from app.core.config import settings as _cfg

    with SyncSessionLocal() as db:
        app = db.query(Application).filter(
            Application.id == uuid_module.UUID(application_id),
            Application.status == ApplicationStatus.sent,
            Application.sent_at.isnot(None),
        ).first()
        if not app:
            return

        followup_setting = db.query(GlobalSetting).filter(GlobalSetting.key == "followup_days").first()
        days_list = json.loads(followup_setting.value) if followup_setting else [2, 4, 6]

        country = "US"
        if app.job_id:
            job_for_fu = db.query(Job).filter(Job.id == app.job_id).first()
            if job_for_fu:
                country = job_for_fu.country or "US"

        _profile = db.query(Profile).filter(Profile.id == app.profile_id).first()
        sender_email = app.sender_email

        _r = _redis.from_url(_cfg.REDIS_URL)
        lock = _r.lock("schedule_slot_lock", timeout=30)

        last_fu_slot = None
        for i, days in enumerate(days_list, start=1):
            # Idempotent — skip if already created
            existing = db.query(ApplicationFollowup).filter(
                ApplicationFollowup.application_id == app.id,
                ApplicationFollowup.follow_up_number == i,
            ).first()
            if existing:
                last_fu_slot = existing.scheduled_at
                continue

            template_type = getattr(TemplateType, f"job_followup_{i}", None)
            template = None
            if template_type:
                any_template = db.query(EmailTemplate).filter(
                    EmailTemplate.template_type == template_type,
                    EmailTemplate.is_default == True,
                ).first()
                if any_template and not any_template.is_active:
                    print(f"[Applicator] Follow-up {i} template is disabled — skipping")
                    continue
                if any_template and any_template.is_active:
                    template = any_template

            fu_tracking_id = secrets.token_hex(16)
            with lock:
                scheduled = get_followup_datetime(
                    app.sent_at, days, country,
                    sender_email=sender_email,
                    after=last_fu_slot,
                )
                last_fu_slot = scheduled

                fu_original_subject = app.subject.split(" — ")[0].strip() if " — " in app.subject else app.subject
                _company_name = job_for_fu.company_name if job_for_fu else ""
                fu_content = generate_followup_email(
                    original_subject=fu_original_subject,
                    company_name=_company_name,
                    profile_name=_profile.name if _profile else "",
                    followup_number=i,
                    template_body=template.body if template else f"Hi,\n\nFollowing up on my application.\n\nBest regards,\n{{name}}",
                    hiring_person_name=app.to_name,
                )
                db.add(ApplicationFollowup(
                    application_id=app.id,
                    follow_up_number=i,
                    subject=fu_content.get("subject", f"Re: {app.subject}"),
                    body=fu_content.get("body", ""),
                    tracking_id=fu_tracking_id,
                    scheduled_at=scheduled,
                    status="pending",
                ))
                db.flush()

        db.commit()
        print(f"[Applicator] Follow-ups scheduled for application {application_id}")


@celery_app.task(name="app.tasks.applicator.send_followup_task")
def send_followup_task(followup_id: str):
    """Send a scheduled follow-up using the same sender as the original application."""
    from app.models.application import Application, ApplicationFollowup
    from app.models.profile import ProfileEmail, Profile
    from app.services.gmail_service import send_email

    with SyncSessionLocal() as db:
        fu = db.query(ApplicationFollowup).filter(
            ApplicationFollowup.id == uuid_module.UUID(followup_id)
        ).with_for_update(skip_locked=True).first()
        if not fu or fu.status in ("sent", "sending", "cancelled"):
            return

        app = db.query(Application).filter(Application.id == fu.application_id).first()
        if not app:
            fu.status = "cancelled"
            db.commit()
            return

        # Skip if recipient already replied — don't follow up with someone who responded
        if app.replied_at:
            fu.status = "cancelled"
            db.commit()
            return

        sender_email = app.sender_email
        sending_token_json = None

        if sender_email:
            pe = db.query(ProfileEmail).filter(ProfileEmail.email == sender_email).first()
            if pe and pe.gmail_token:
                sending_token_json = pe.gmail_token

            if not sending_token_json:
                from app.models.email_account import EmailAccount
                ea = db.query(EmailAccount).filter(
                    EmailAccount.email == sender_email,
                    EmailAccount.is_authorized == True,
                ).first()
                if ea and ea.gmail_token:
                    sending_token_json = ea.gmail_token

        if not sending_token_json:
            print(f"[Applicator] No token for follow-up {followup_id} — cancelling")
            fu.status = "cancelled"
            db.commit()
            return

        _profile = db.query(Profile).filter(Profile.id == app.profile_id).first()

        try:
            send_email(
                token_json=sending_token_json,
                sender=sender_email,
                to=app.to_email,
                subject=fu.subject,
                body=fu.body,
                tracking_pixel_url=None,
                sender_name=_profile.name if _profile else None,
            )
            fu.status = "sent"
            fu.sent_at = datetime.utcnow()
            # Update job status to followed_up
            _job = db.query(Job).filter(Job.id == app.job_id).first()
            if _job:
                _job.status = JobStatus.followed_up
            db.commit()
        except Exception as e:
            print(f"[Applicator] Follow-up send error: {e}")


@celery_app.task(name="app.tasks.applicator.requeue_ready_jobs_task")
def requeue_ready_jobs_task():
    """
    Recovery task — runs every 15 minutes via beat. Does two things:
    1. Re-queues apply_job_task for any 'ready' or 'matched' job with no Application record
       (jobs dropped when worker restarts mid-flight).
    2. Skips 'researching' jobs older than 24h with no contact found — Hunter keys
       may be exhausted; these jobs should not block the pipeline indefinitely.
    """
    from app.models.job import Job, JobStatus, JobContact
    from app.models.application import Application, ApplicationStatus, ApplicationFollowup
    import datetime

    with SyncSessionLocal() as db:
        # 1. Re-queue ready/matched jobs with no application
        stuck = db.query(Job).filter(Job.status.in_([JobStatus.ready, JobStatus.matched])).all()
        queued = 0
        status_fixed = 0
        for job in stuck:
            app = db.query(Application).filter(Application.job_id == job.id).first()
            if not app:
                apply_job_task.delay(str(job.id))
                queued += 1
            else:
                # Job is 'ready' but already has an application — sync job status from application
                if app.status == ApplicationStatus.sent:
                    job.status = JobStatus.applied
                elif app.status in (ApplicationStatus.scheduled, ApplicationStatus.pending_approval, ApplicationStatus.sending):
                    job.status = JobStatus.scheduled
                # rejected/failed apps: leave job in ready so it can be re-applied
                status_fixed += 1
        if queued:
            print(f"[Requeue] Re-queued {queued} stuck ready/matched jobs")
        if status_fixed:
            db.commit()
            print(f"[Requeue] Fixed status for {status_fixed} ready jobs that already had applications")

        # 1b. Recover jobs stuck in 'scheduled' with no Application record
        # (apply_job_task failed after locking the job but before creating the Application)
        from datetime import timedelta
        stuck_scheduled = db.query(Job).filter(Job.status == JobStatus.scheduled).all()
        recovered = 0
        for job in stuck_scheduled:
            has_app = db.query(Application).filter(Application.job_id == job.id).first()
            if not has_app:
                job.status = JobStatus.ready
                recovered += 1
        if recovered:
            db.commit()
            print(f"[Requeue] Recovered {recovered} jobs stuck in 'scheduled' with no application")

        # 2. Backfill missing follow-ups for sent applications — run synchronously
        # (not via .delay) so a busy queue can't cause follow-ups to be silently lost
        sent_apps = db.query(Application).filter(
            Application.status == ApplicationStatus.sent,
            Application.sent_at.isnot(None),
        ).all()
        fu_fixed = 0
        for sent_app in sent_apps:
            fu_count = db.query(ApplicationFollowup).filter(
                ApplicationFollowup.application_id == sent_app.id,
            ).count()
            if fu_count == 0:
                try:
                    schedule_followups_task(str(sent_app.id))
                    fu_fixed += 1
                except Exception as e:
                    print(f"[Requeue] Failed to backfill follow-ups for {sent_app.id}: {e}")
        if fu_fixed:
            print(f"[Requeue] Backfilled follow-ups for {fu_fixed} sent applications")

        # 2b. Auto-approve overdue pending_approval applications (past scheduled_at)
        # These pile up when approval is enabled but nobody clicks approve.
        # Any application whose scheduled_at is in the past and still pending gets promoted.
        overdue = db.query(Application).filter(
            Application.status == ApplicationStatus.pending_approval,
            Application.scheduled_at <= datetime.utcnow(),
            Application.sent_at.is_(None),
        ).all()
        approved = 0
        for oa in overdue:
            oa.status = ApplicationStatus.scheduled
            approved += 1
        if approved:
            db.commit()
            print(f"[Requeue] Auto-approved {approved} overdue pending_approval applications")

        # 3. Skip researching jobs with no contact found after 24h
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        old_researching = db.query(Job).filter(
            Job.status == JobStatus.researching,
            Job.scraped_at <= cutoff,
        ).all()
        skipped = 0
        for job in old_researching:
            contact = db.query(JobContact).filter(
                JobContact.job_id == job.id,
                JobContact.email != None,
            ).first()
            if not contact:
                job.status = JobStatus.skipped
                skipped += 1
        if skipped:
            db.commit()
            print(f"[Requeue] Skipped {skipped} researching jobs with no contact after 24h")


@celery_app.task(name="app.tasks.applicator.send_scheduled_applications_task")
def send_scheduled_applications_task():
    """
    Picks up due applications/follow-ups and dispatches them ONE AT A TIME
    with a minimum 5-minute gap (+ random jitter) between each send.
    This prevents Gmail from seeing a burst of outbound emails and marking
    the account as spam.
    """
    import random as _random
    from app.models.application import Application, ApplicationStatus, ApplicationFollowup
    from app.services.scheduler_service import _get_limits

    with SyncSessionLocal() as db:
        from app.models.settings import GlobalSetting
        from datetime import timedelta
        now = datetime.utcnow()

        # Rescue any applications stuck in "sending" for more than 5 minutes
        # (worker crashed before completing) — reset them to "scheduled" for retry
        stuck_cutoff = now - timedelta(minutes=5)
        stuck = db.query(Application).filter(
            Application.status == ApplicationStatus.sending,
            Application.sent_at.is_(None),
            Application.scheduled_at <= stuck_cutoff,
        ).all()
        for s in stuck:
            print(f"[Scheduler] Rescuing stuck application {s.id} back to scheduled")
            s.status = ApplicationStatus.scheduled
        if stuck:
            db.commit()

        approval_setting = db.query(GlobalSetting).filter(GlobalSetting.key == "approval_enabled_jobs").first()
        approval_enabled = (approval_setting.value == "true") if approval_setting else True

        statuses = [ApplicationStatus.scheduled]
        if not approval_enabled:
            statuses.append(ApplicationStatus.pending_approval)

        # Only send ONE application per scheduler tick (every 5 min) — prevents bursts.
        # Also enforce per-account hourly limit: max 8 emails/hour per sender.
        HOURLY_LIMIT = 8
        from app.models.email_account import EmailAccount as _EA
        from app.models.profile import ProfileEmail as _PE

        app = db.query(Application).filter(
            Application.status.in_(statuses),
            Application.scheduled_at <= now,
            Application.sent_at.is_(None),
        ).order_by(Application.scheduled_at).first()

        app_id = None
        if app:
            # Check hourly rate for this sender before dispatching
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            hour_sent = db.query(Application).filter(
                Application.sender_email == app.sender_email,
                Application.sent_at >= hour_start,
                Application.sent_at <= now,
                Application.status == ApplicationStatus.sent,
            ).count()
            if hour_sent >= HOURLY_LIMIT:
                print(f"[Scheduler] {app.sender_email} hit hourly limit ({hour_sent}/{HOURLY_LIMIT}), skipping tick")
            else:
                # Mark as "sending" immediately so the next scheduler tick won't pick it again
                app.status = ApplicationStatus.sending
                db.commit()
                app_id = str(app.id)

    # Follow-ups are handled exclusively by process_followups_task (followup.py)
    # which uses an atomic bulk UPDATE to claim rows — no duplicate path here.

    if app_id:
        send_application_task.apply_async(args=[app_id], queue="send")
        print(f"[Scheduler] Dispatched application {app_id} → send queue")
