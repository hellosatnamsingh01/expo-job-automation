from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
from datetime import datetime
from app.models.job import Job, JobStatus


@celery_app.task(name="app.tasks.followup.process_followups_task")
def process_followups_task():
    from app.models.application import Application, ApplicationFollowup, ApplicationStatus
    from app.models.profile import Profile, ProfileEmail
    from app.models.email_account import EmailAccount
    from app.services.gmail_service import send_email
    from app.core.config import settings as app_settings
    from sqlalchemy import update

    with SyncSessionLocal() as db:
        now = datetime.utcnow()

        # Atomically claim due follow-ups by setting status → 'sending'
        # This prevents multiple workers from picking up the same row
        result = db.execute(
            update(ApplicationFollowup)
            .where(
                ApplicationFollowup.status == "pending",
                ApplicationFollowup.scheduled_at <= now,
            )
            .values(status="sending")
            .returning(ApplicationFollowup.id)
        )
        claimed_ids = [row[0] for row in result.fetchall()]
        db.commit()

        if not claimed_ids:
            return

        followups = db.query(ApplicationFollowup).filter(
            ApplicationFollowup.id.in_(claimed_ids)
        ).all()

        for fu in followups:
            app = db.query(Application).filter(Application.id == fu.application_id).first()
            if not app or app.replied_at or fu.follow_up_number > 3:
                fu.status = "cancelled"
                db.commit()
                continue

            # Always use the exact same sender as the original email — NEVER switch accounts
            sender_email = app.sender_email
            sending_token_json = None

            if sender_email:
                pe = db.query(ProfileEmail).filter(ProfileEmail.email == sender_email).first()
                if pe and pe.gmail_token:
                    sending_token_json = pe.gmail_token
                if not sending_token_json:
                    ea = db.query(EmailAccount).filter(
                        EmailAccount.email == sender_email,
                        EmailAccount.is_authorized == True,
                    ).first()
                    if ea and ea.gmail_token:
                        sending_token_json = ea.gmail_token

            if not sending_token_json:
                print(f"[Followup] No Gmail token for {sender_email} — cancelling follow-up {fu.id}")
                fu.status = "cancelled"
                db.commit()
                continue

            profile = db.query(Profile).filter(Profile.id == app.profile_id).first()
            sender_name = profile.name if profile else None

            tracking_url = f"{app_settings.TRACKING_PIXEL_URL}/pixel/{fu.tracking_id}" if fu.tracking_id else None
            try:
                send_email(
                    token_json=sending_token_json,
                    sender=sender_email,
                    to=app.to_email,
                    subject=fu.subject,
                    body=fu.body,
                    tracking_pixel_url=tracking_url,
                    thread_id=app.gmail_thread_id,
                    sender_name=sender_name,
                )
                fu.status = "sent"
                fu.sent_at = now
                app.follow_up_count = fu.follow_up_number
                if fu.follow_up_number >= 3:
                    app.status = ApplicationStatus.cold
                # Update job status to followed_up
                _job = db.query(Job).filter(Job.id == app.job_id).first()
                if _job and _job.status not in (JobStatus.replied,):
                    _job.status = JobStatus.followed_up
            except Exception as e:
                print(f"[Followup] Error sending FU#{fu.follow_up_number} for app {app.id}: {e}")
                fu.status = "pending"  # revert so it retries next cycle

            db.commit()
