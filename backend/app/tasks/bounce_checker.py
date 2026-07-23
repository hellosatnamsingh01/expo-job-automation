"""
Polls each sender Gmail inbox for bounce / delivery-failure notifications
(from mailer-daemon / postmaster) and marks the matching application + job
as 'bounced' so the user can update the contact and re-send manually.
"""
from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
from datetime import datetime, timedelta
import re


# Subjects that indicate a hard bounce / blocked message
_BOUNCE_SUBJECTS = [
    "delivery status notification",
    "mail delivery failed",
    "mail delivery failure",
    "undeliverable",
    "message blocked",
    "delivery failure",
    "returned mail",
    "auto-reply",
]

# Senders that send bounce notifications
_BOUNCE_SENDERS = [
    "mailer-daemon",
    "postmaster",
    "noreply@google.com",
    "noreply@googlemail.com",
]


def _extract_bounced_email(snippet: str, body: str) -> str | None:
    """Try to pull the failed recipient address out of the bounce body."""
    text = (snippet or "") + " " + (body or "")
    # Most common pattern: "to <email>" or "for <email>" in bounce bodies
    for pattern in [
        r"(?:to|for|recipient|address)\s*[:<]?\s*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
        r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    ]:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            # Skip common system addresses
            if not any(skip in m.lower() for skip in ["mailer-daemon", "postmaster", "noreply", "google"]):
                return m.lower()
    return None


@celery_app.task(name="app.tasks.bounce_checker.check_bounces_task")
def check_bounces_task():
    from app.models.application import Application, ApplicationStatus
    from app.models.profile import ProfileEmail
    from app.models.email_account import EmailAccount
    from app.models.job import Job, JobStatus
    from app.services.gmail_service import get_gmail_service

    with SyncSessionLocal() as db:
        # Get all active sender emails that have a Gmail token
        profile_emails = db.query(ProfileEmail).filter(
            ProfileEmail.gmail_token.isnot(None),
        ).all()

        email_accounts = db.query(EmailAccount).filter(
            EmailAccount.gmail_token.isnot(None),
            EmailAccount.is_active == True,
        ).all()

        # Build list of (email, token) pairs — deduplicated
        checked = set()
        senders = []
        for pe in profile_emails:
            if pe.email not in checked and pe.gmail_token:
                senders.append((pe.email, pe.gmail_token))
                checked.add(pe.email)
        for ea in email_accounts:
            if ea.email not in checked and ea.gmail_token:
                senders.append((ea.email, ea.gmail_token))
                checked.add(ea.email)

        detected = 0
        for sender_email, token_json in senders:
            try:
                service = get_gmail_service(token_json)
                if not service:
                    continue

                # Search inbox for unread bounce messages in the last 48 hours
                result = service.users().messages().list(
                    userId="me",
                    q="is:unread (from:mailer-daemon OR from:postmaster) newer_than:2d",
                    maxResults=50,
                ).execute()

                messages = result.get("messages", [])
                for msg_ref in messages:
                    try:
                        msg = service.users().messages().get(
                            userId="me",
                            id=msg_ref["id"],
                            format="full",
                        ).execute()

                        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                        subject = headers.get("subject", "").lower()
                        from_addr = headers.get("from", "").lower()
                        snippet = msg.get("snippet", "")

                        # Confirm it's actually a bounce
                        is_bounce_sender = any(b in from_addr for b in _BOUNCE_SENDERS)
                        is_bounce_subject = any(s in subject for s in _BOUNCE_SUBJECTS)
                        if not (is_bounce_sender or is_bounce_subject):
                            continue

                        # Extract body text for email parsing
                        body = ""
                        payload = msg.get("payload", {})
                        parts = payload.get("parts", [payload])
                        for part in parts:
                            if part.get("mimeType") == "text/plain":
                                import base64
                                data = part.get("body", {}).get("data", "")
                                if data:
                                    body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                                    break

                        bounced_email = _extract_bounced_email(snippet, body)
                        if not bounced_email:
                            continue

                        # Find the sent application for this sender + recipient
                        app = db.query(Application).filter(
                            Application.sender_email == sender_email,
                            Application.to_email == bounced_email,
                            Application.status.in_([
                                ApplicationStatus.sent,
                                ApplicationStatus.opened,
                                ApplicationStatus.failed,
                            ]),
                        ).order_by(Application.sent_at.desc()).first()

                        if not app:
                            # Mark as read anyway so we don't keep processing it
                            service.users().messages().modify(
                                userId="me", id=msg_ref["id"],
                                body={"removeLabelIds": ["UNREAD"]},
                            ).execute()
                            continue

                        # Mark application bounced
                        app.status = ApplicationStatus.bounced
                        app.bounced_at = datetime.utcnow() if hasattr(app, "bounced_at") else None

                        # Mark job bounced
                        if app.job_id:
                            job = db.query(Job).filter(Job.id == app.job_id).first()
                            if job and job.status not in (JobStatus.replied,):
                                job.status = JobStatus.bounced

                        db.commit()
                        detected += 1
                        print(f"[BounceChecker] Bounced: {bounced_email} (sender: {sender_email})")

                        # Mark the bounce notification as read
                        service.users().messages().modify(
                            userId="me", id=msg_ref["id"],
                            body={"removeLabelIds": ["UNREAD"]},
                        ).execute()

                    except Exception as e:
                        print(f"[BounceChecker] Error processing message {msg_ref['id']}: {e}")
                        continue

            except Exception as e:
                print(f"[BounceChecker] Error checking inbox for {sender_email}: {e}")
                continue

        print(f"[BounceChecker] Done — {detected} bounce(s) detected")
        return detected
