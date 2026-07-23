from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid, json

from app.db.base import get_db
from app.models.email_account import EmailAccount
from app.models.profile import ProfileEmail
from app.models.user import Permission
from app.core.deps import require_permission
from app.core.config import settings

router = APIRouter()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

# In-memory store for PKCE code verifiers keyed by OAuth state
# (single-process uvicorn — safe for local/dev use)
_pkce_store: dict = {}


class EmailAccountCreate(BaseModel):
    display_name: str
    email: str
    client_id: str
    client_secret: str
    purpose: Optional[str] = "job_applications"  # "job_applications" | "b2b" | "both"


class EmailAccountUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    purpose: Optional[str] = None


def _build_flow(client_id: str, client_secret: str):
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GMAIL_REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.GMAIL_REDIRECT_URI,
    )


@router.get("/")
async def list_email_accounts(
    current_user=Depends(require_permission(Permission.view_platforms)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EmailAccount).order_by(EmailAccount.created_at.desc()))
    accounts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "email": a.email,
            "display_name": a.display_name,
            "is_active": a.is_active,
            "is_authorized": a.is_authorized,
            "has_credentials": bool(a.client_id and a.client_secret),
            "purpose": a.purpose or "job_applications",
            "created_at": a.created_at,
        }
        for a in accounts
    ]


@router.post("/")
async def create_email_account(
    data: EmailAccountCreate,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    """Add an email account with its own Gmail OAuth credentials."""
    existing = await db.execute(select(EmailAccount).where(EmailAccount.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, detail=f"Account {data.email} already exists")
    account = EmailAccount(
        email=data.email,
        display_name=data.display_name,
        client_id=data.client_id,
        client_secret=data.client_secret,
        is_active=True,
        is_authorized=False,
        purpose=data.purpose or "job_applications",
    )
    db.add(account)
    await db.commit()
    return {"id": str(account.id), "message": "Account added. Now connect it via Gmail OAuth."}


@router.patch("/{account_id}")
async def update_email_account(
    account_id: uuid.UUID,
    data: EmailAccountUpdate,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EmailAccount).where(EmailAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, detail="Not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(account, field, value)
    await db.commit()
    return {"message": "Updated"}


@router.get("/profile-emails")
async def list_profile_emails(
    current_user=Depends(require_permission(Permission.view_platforms)),
    db: AsyncSession = Depends(get_db),
):
    from app.models.profile import Profile
    result = await db.execute(
        select(ProfileEmail, Profile.name)
        .join(Profile, ProfileEmail.profile_id == Profile.id)
        .order_by(Profile.name)
    )
    rows = result.all()

    # Auto-sync: copy token from EmailAccount → ProfileEmail when they share the same address
    synced = False
    for pe, name in rows:
        if not pe.gmail_token:
            ea_r = await db.execute(
                select(EmailAccount).where(
                    EmailAccount.email == pe.email,
                    EmailAccount.is_authorized == True,
                    EmailAccount.gmail_token.isnot(None),
                )
            )
            ea = ea_r.scalar_one_or_none()
            if ea:
                pe.gmail_token = ea.gmail_token
                synced = True
    if synced:
        await db.commit()

    return [
        {
            "id": str(pe.id),
            "email": pe.email,
            "profile_id": str(pe.profile_id),
            "profile_name": name,
            "is_primary": pe.is_primary,
            "connected": bool(pe.gmail_token),
        }
        for pe, name in rows
    ]


@router.get("/connect")
async def connect_gmail(
    account_id: str = None,
    profile_email_id: str = None,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    """Start Gmail OAuth flow using per-account credentials if available."""
    import os, secrets, hashlib, base64
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    client_id = None
    client_secret = None

    if account_id:
        result = await db.execute(select(EmailAccount).where(EmailAccount.id == uuid.UUID(account_id)))
        account = result.scalar_one_or_none()
        if account and account.client_id:
            client_id = account.client_id
            client_secret = account.client_secret

    if not client_id:
        client_id = settings.GMAIL_CLIENT_ID
        client_secret = settings.GMAIL_CLIENT_SECRET

    if client_id == "your-gmail-client-id":
        raise HTTPException(400, detail="Gmail credentials not configured.")

    state = f"{account_id or 'new'}|{profile_email_id or ''}"
    flow = _build_flow(client_id, client_secret)

    # Generate PKCE code verifier + challenge
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    # Store verifier so callback can use it
    _pkce_store[state] = {
        "code_verifier": code_verifier,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return {"auth_url": auth_url}


@router.get("/callback")
async def gmail_callback(
    code: str,
    state: str = "new|",
    db: AsyncSession = Depends(get_db),
):
    import os, httpx as _httpx
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    try:
        parts = state.split("|", 1)
        account_id_str = parts[0] if parts else "new"
        profile_email_id_str = parts[1] if len(parts) > 1 else ""

        # Retrieve PKCE verifier + credentials stored during /connect
        pkce = _pkce_store.pop(state, None)
        if pkce:
            client_id = pkce["client_id"]
            client_secret = pkce["client_secret"]
            code_verifier = pkce["code_verifier"]
        else:
            # Fallback: load from DB
            client_id = settings.GMAIL_CLIENT_ID
            client_secret = settings.GMAIL_CLIENT_SECRET
            code_verifier = None
            if account_id_str and account_id_str != "new":
                try:
                    r = await db.execute(select(EmailAccount).where(EmailAccount.id == uuid.UUID(account_id_str)))
                    acct = r.scalar_one_or_none()
                    if acct and acct.client_id:
                        client_id = acct.client_id
                        client_secret = acct.client_secret
                except Exception:
                    pass

        flow = _build_flow(client_id, client_secret)

        # Exchange code for token — include code_verifier if PKCE was used
        fetch_kwargs = {"code": code}
        if code_verifier:
            fetch_kwargs["code_verifier"] = code_verifier
        flow.fetch_token(**fetch_kwargs)
        creds = flow.credentials

        user_info = _httpx.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
        ).json()
        gmail_email = user_info.get("email", "")
        display_name = user_info.get("name", gmail_email)

        token_json = json.dumps({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or []),
        })

        # If profile_email_id, link to that ProfileEmail
        if profile_email_id_str:
            try:
                pe_result = await db.execute(select(ProfileEmail).where(ProfileEmail.id == uuid.UUID(profile_email_id_str)))
                pe = pe_result.scalar_one_or_none()
                if pe:
                    pe.gmail_token = token_json
                    await db.commit()
                    return RedirectResponse(f"http://localhost:3005/dashboard/email-accounts?connected={gmail_email}&profile=1")
            except Exception:
                pass

        # Update or create EmailAccount
        if account_id_str and account_id_str != "new":
            try:
                result = await db.execute(select(EmailAccount).where(EmailAccount.id == uuid.UUID(account_id_str)))
                account = result.scalar_one_or_none()
                if account:
                    account.gmail_token = token_json
                    account.is_authorized = True
                    account.display_name = display_name
                    await db.commit()
                    return RedirectResponse(f"http://localhost:3005/dashboard/email-accounts?connected={gmail_email}")
            except Exception:
                pass

        existing = await db.execute(select(EmailAccount).where(EmailAccount.email == gmail_email))
        account = existing.scalar_one_or_none()
        if account:
            account.gmail_token = token_json
            account.is_authorized = True
            account.display_name = display_name
        else:
            db.add(EmailAccount(
                email=gmail_email,
                display_name=display_name,
                gmail_token=token_json,
                is_active=True,
                is_authorized=True,
            ))

        # Auto-sync: copy token to any ProfileEmail with the same address
        pe_rows = await db.execute(select(ProfileEmail).where(ProfileEmail.email == gmail_email))
        for pe in pe_rows.scalars().all():
            pe.gmail_token = token_json

        await db.commit()
        return RedirectResponse(f"http://localhost:3005/dashboard/email-accounts?connected={gmail_email}")

    except Exception as e:
        return RedirectResponse(f"http://localhost:3005/dashboard/email-accounts?error={str(e)[:100]}")


@router.post("/{account_id}/send-test")
async def send_test_email(
    account_id: uuid.UUID,
    body: dict,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    """Send a test email from this account's connected Gmail."""
    result = await db.execute(select(EmailAccount).where(EmailAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, detail="Account not found")
    if not account.gmail_token:
        raise HTTPException(400, detail="Account is not connected to Gmail yet. Complete OAuth first.")

    to_email = body.get("to_email", "").strip()
    if not to_email:
        raise HTTPException(400, detail="Recipient email (to_email) is required")

    try:
        import base64
        from email.mime.text import MIMEText
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_data = json.loads(account.gmail_token)
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", []),
        )

        service = build("gmail", "v1", credentials=creds)

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 24px; border: 1px solid #e5e7eb; border-radius: 12px;">
          <h2 style="color: #1d4ed8; margin-bottom: 8px;">✅ Test Email from Expandimo</h2>
          <p style="color: #374151; font-size: 15px;">This is a test email sent from <strong>{account.email}</strong> via the Expandimo Outreach Engine.</p>
          <p style="color: #6b7280; font-size: 13px; margin-top: 16px;">If you received this email, the Gmail connection is working correctly and outreach emails can be sent from this account.</p>
          <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;" />
          <p style="color: #9ca3af; font-size: 11px;">Sent by Expandimo · {account.display_name or account.email}</p>
        </div>
        """

        msg = MIMEText(html_body, "html")
        msg["to"] = to_email
        msg["from"] = f"{account.display_name or 'Expandimo'} <{account.email}>"
        msg["subject"] = "✅ Test Email — Expandimo Outreach Engine"

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()

        return {"message": f"Test email sent to {to_email}"}

    except Exception as e:
        raise HTTPException(500, detail=f"Failed to send email: {str(e)[:200]}")


@router.delete("/{account_id}")
async def delete_email_account(
    account_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EmailAccount).where(EmailAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, detail="Not found")
    await db.delete(account)
    await db.commit()
    return {"message": "Disconnected"}


@router.patch("/{account_id}/toggle")
async def toggle_email_account(
    account_id: uuid.UUID,
    current_user=Depends(require_permission(Permission.manage_platforms)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EmailAccount).where(EmailAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, detail="Not found")
    account.is_active = not account.is_active
    await db.commit()
    return {"is_active": account.is_active}
