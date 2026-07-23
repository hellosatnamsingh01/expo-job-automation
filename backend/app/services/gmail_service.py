import json
import base64
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from app.core.config import settings


def get_gmail_service(token_json: str):
    token_data = json.loads(token_json)
    client_id = token_data.get("client_id") or settings.GMAIL_CLIENT_ID
    client_secret = token_data.get("client_secret") or settings.GMAIL_CLIENT_SECRET
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client_id,
        client_secret=client_secret,
        scopes=token_data.get("scopes"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def _ensure_signature(body: str, sender_name: str) -> str:
    if not sender_name:
        return body
    stripped = body.rstrip()
    closings = ["best,", "thanks,", "regards,", "cheers,", "sincerely,", "warm regards,", "kind regards,"]
    last_line = stripped.split("\n")[-1].strip().lower()
    if last_line in closings:
        return stripped + "\n" + sender_name
    return body


def build_email_message(
    sender: str,
    to: str,
    subject: str,
    body: str,
    tracking_pixel_url: str = None,  # kept for API compat but ignored
    pdf_path: str = None,
    thread_id: str = None,
    sender_name: str = None,
) -> dict:
    import uuid as _uuid
    from email.utils import formatdate

    body = _ensure_signature(body, sender_name)
    has_attachment = bool(pdf_path and os.path.exists(pdf_path))

    if has_attachment:
        msg = MIMEMultipart("mixed")
        if sender_name:
            msg["From"] = f"{sender_name} <{sender}>"
        else:
            msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg["Reply-To"] = sender
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = f"<{_uuid.uuid4()}@{sender.split('@')[1]}>"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="pdf")
            part.add_header("Content-Disposition", "attachment", filename=os.path.basename(pdf_path))
            msg.attach(part)
    else:
        # Pure plain text — no HTML part, no tracking pixel
        # This is the most deliverable format for cold outreach
        msg = MIMEText(body, "plain", "utf-8")
        if sender_name:
            msg["From"] = f"{sender_name} <{sender}>"
        else:
            msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg["Reply-To"] = sender
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = f"<{_uuid.uuid4()}@{sender.split('@')[1]}>"

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    return payload


def send_email(
    token_json: str,
    sender: str,
    to: str,
    subject: str,
    body: str,
    tracking_pixel_url: str = None,
    pdf_path: str = None,
    thread_id: str = None,
    sender_name: str = None,
) -> dict:
    service = get_gmail_service(token_json)
    message = build_email_message(sender, to, subject, body, tracking_pixel_url, pdf_path, thread_id, sender_name)
    result = service.users().messages().send(userId="me", body=message).execute()
    return result
