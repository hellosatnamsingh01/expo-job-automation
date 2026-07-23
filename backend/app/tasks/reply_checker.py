"""
Polls Gmail threads for all sent-but-unreplied applications and marks them replied
when a message from someone other than the sender appears in the thread.
"""
from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
from datetime import datetime


@celery_app.task(name="app.tasks.reply_checker.check_replies_task")
def check_replies_task():
    from app.models.application import Application, ApplicationStatus
    from app.models.profile import ProfileEmail
    from app.models.email_account import EmailAccount
    from app.models.job import Job, JobStatus
    from app.services.gmail_service import get_gmail_service

    with SyncSessionLocal() as db:
        # All sent applications that haven't been replied to yet and have a thread ID
        apps = db.query(Application).filter(
            Application.status.in_([ApplicationStatus.sent, ApplicationStatus.opened]),
            Application.replied_at.is_(None),
            Application.gmail_thread_id.isnot(None),
        ).all()

        if not apps:
            return

        # Group by sending email to reuse the same Gmail service instance
        for app in apps:
            try:
                # Resolve the Gmail token for this application
                profile_email = db.query(ProfileEmail).filter(
                    ProfileEmail.id == app.profile_email_id
                ).first() if app.profile_email_id else None

                token_json = profile_email.gmail_token if profile_email else None
                sender_email = profile_email.email if profile_email else None

                if not token_json:
                    ea = None
                    if sender_email:
                        ea = db.query(EmailAccount).filter(
                            EmailAccount.email == sender_email,
                            EmailAccount.is_authorized == True,
                        ).first()
                    if not ea:
                        ea = db.query(EmailAccount).filter(
                            EmailAccount.is_authorized == True,
                            EmailAccount.is_active == True,
                        ).first()
                    if ea and ea.gmail_token:
                        token_json = ea.gmail_token
                        sender_email = ea.email

                if not token_json:
                    continue

                service = get_gmail_service(token_json)

                # Fetch the thread
                thread = service.users().threads().get(
                    userId="me",
                    id=app.gmail_thread_id,
                    format="metadata",
                    metadataHeaders=["From", "Date"],
                ).execute()

                messages = thread.get("messages", [])

                # A reply exists if there are >1 messages in the thread
                # AND at least one message is NOT from our sender
                replied = False
                for msg in messages[1:]:  # skip the first message (our outbound email)
                    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                    from_header = headers.get("From", "").lower()
                    if sender_email and sender_email.lower() not in from_header:
                        replied = True
                        break

                if replied:
                    app.status = ApplicationStatus.replied
                    app.replied_at = datetime.utcnow()

                    # Update job
                    job = db.query(Job).filter(Job.id == app.job_id).first()
                    if job:
                        job.status = JobStatus.replied
                        job.has_reply = True

                    print(f"[ReplyChecker] Reply detected for application {app.id} ({app.subject})")
                    try:
                        from app.services.alert_service import create_alert
                        from app.models.alert import AlertType, AlertSeverity
                        company = job.company_name if job else "unknown"
                        create_alert(
                            type=AlertType.reply_received,
                            severity=AlertSeverity.info,
                            title=f"Reply received from {company}",
                            message=f"Subject: {app.subject}\nSent to: {app.to_email}",
                            source="Job Applications",
                        )
                    except Exception:
                        pass

            except Exception as e:
                print(f"[ReplyChecker] Error checking app {app.id}: {e}")
                continue

        db.commit()
