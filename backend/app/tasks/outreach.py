from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
import secrets
from datetime import datetime


@celery_app.task(name="app.tasks.outreach.send_b2b_email_task")
def send_b2b_email_task(lead_id: str):
    import uuid
    from app.models.lead import Lead, LeadStatus, LeadActivity
    from app.models.email_account import EmailAccount
    from app.models.email_template import EmailTemplate, TemplateType
    from app.models.settings import GlobalSetting
    from app.models.user import User
    from app.services.ai_service import generate_b2b_email
    from app.services.scheduler_service import get_send_datetime
    from app.core.config import settings as app_settings

    with SyncSessionLocal() as db:
        lead = db.query(Lead).filter(Lead.id == uuid.UUID(lead_id)).first()
        if not lead or not lead.contact_email:
            return

        # Industry-specific template first, fall back to generic (industry=NULL)
        template = db.query(EmailTemplate).filter(
            EmailTemplate.template_type == TemplateType.b2b_initial,
            EmailTemplate.industry == lead.industry,
            EmailTemplate.is_default == True,
            EmailTemplate.is_active == True,
        ).first()
        if not template:
            template = db.query(EmailTemplate).filter(
                EmailTemplate.template_type == TemplateType.b2b_initial,
                EmailTemplate.industry.is_(None),
                EmailTemplate.is_default == True,
                EmailTemplate.is_active == True,
            ).first()
        tpl_subject = template.subject if template else "Quick introduction from Expandimo"
        tpl_body = template.body if template else "Hi {name},\n\nI wanted to reach out.\n\nBest regards"

        sender_name = "Expandimo Team"
        sender_email_obj = None

        # If lead already has an assigned sender, respect it
        if lead.sender_email_id:
            sender_email_obj = db.query(EmailAccount).filter(EmailAccount.id == lead.sender_email_id).first()

        # Otherwise pick from B2B-purpose accounts (round-robin by least recently used)
        if not sender_email_obj or not sender_email_obj.gmail_token:
            from sqlalchemy import func
            b2b_accounts = db.query(EmailAccount).filter(
                EmailAccount.is_active == True,
                EmailAccount.is_authorized == True,
                EmailAccount.gmail_token.isnot(None),
                EmailAccount.purpose.in_(["b2b", "both"]),
            ).all()
            if not b2b_accounts:
                print(f"[B2B] No B2B email accounts configured — add accounts with purpose='b2b' or 'both'")
                return
            # Pick account with fewest sends today (simple round-robin via sent_at counts)
            from app.models.lead import Lead as LeadModel
            from datetime import timedelta
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            best = None
            best_count = 999999
            for acct in b2b_accounts:
                count = db.query(LeadModel).filter(
                    LeadModel.score_breakdown["_sender_email_id"].astext == str(acct.id),
                    LeadModel.sent_at >= today,
                ).count()
                if count < best_count:
                    best_count = count
                    best = acct
            sender_email_obj = best

        if not sender_email_obj or not sender_email_obj.gmail_token:
            print(f"[B2B] No B2B sender available for lead {lead_id}")
            return

        email_content = generate_b2b_email(
            company_name=lead.company_name,
            industry=lead.industry or "",
            country=lead.country or "",
            contact_name=lead.contact_name or "",
            template_subject=tpl_subject,
            template_body=tpl_body,
            sender_name=sender_name,
        )

        approval_setting = db.query(GlobalSetting).filter(GlobalSetting.key == "approval_enabled_b2b").first()
        approval_enabled = (approval_setting.value == "true") if approval_setting else True

        scheduled_at = get_send_datetime(lead.country or "US")
        tracking_id = secrets.token_hex(16)

        lead.status = LeadStatus.pending_approval if approval_enabled else LeadStatus.scheduled
        lead.scheduled_at = scheduled_at
        lead.tracking_id = tracking_id
        lead.score_breakdown = lead.score_breakdown or {}
        lead.score_breakdown["_pending_subject"] = email_content.get("subject", "")
        lead.score_breakdown["_pending_body"] = email_content.get("body", "")
        lead.score_breakdown["_sender_email_id"] = str(sender_email_obj.id)

        db.add(LeadActivity(
            lead_id=lead.id,
            action="email_scheduled",
            detail=f"Subject: {email_content.get('subject')} | To: {lead.contact_email}",
        ))
        db.commit()


B2B_DAILY_LIMIT = 15


@celery_app.task(name="app.tasks.outreach.send_scheduled_b2b_task")
def send_scheduled_b2b_task():
    """Send ONE due B2B lead per tick. Enforces 15/day per sender. Never bursts."""
    import uuid
    from app.models.lead import Lead, LeadStatus, LeadActivity
    from app.models.email_account import EmailAccount
    from app.services.gmail_service import send_email
    from app.core.config import settings as app_settings
    from sqlalchemy import func
    from datetime import timedelta

    with SyncSessionLocal() as db:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Rescue leads stuck in "sending" for >5 min (worker crash recovery)
        stuck_cutoff = now - timedelta(minutes=5)
        stuck = db.query(Lead).filter(
            Lead.status == LeadStatus.sending,
            Lead.sent_at.is_(None),
            Lead.scheduled_at <= stuck_cutoff,
        ).all()
        for s in stuck:
            s.status = LeadStatus.scheduled
        if stuck:
            db.commit()

        # Pick ONE due lead
        lead = db.query(Lead).filter(
            Lead.status == LeadStatus.scheduled,
            Lead.scheduled_at <= now,
            Lead.sent_at.is_(None),
        ).order_by(Lead.scheduled_at).first()

        if not lead:
            return

        breakdown = lead.score_breakdown or {}
        subject = breakdown.get("_pending_subject", "")
        body = breakdown.get("_pending_body", "")
        sender_id = breakdown.get("_sender_email_id")
        if not sender_id:
            lead.status = LeadStatus.failed
            db.commit()
            return

        sender = db.query(EmailAccount).filter(EmailAccount.id == uuid.UUID(sender_id)).first()
        if not sender or not sender.gmail_token:
            lead.status = LeadStatus.failed
            db.commit()
            return

        # Enforce daily limit for this sender
        sent_today = db.query(func.count(Lead.id)).filter(
            Lead.score_breakdown["_sender_email_id"].astext == str(sender.id),
            Lead.sent_at >= today_start,
            Lead.sent_at < today_end,
        ).scalar() or 0
        if sent_today >= B2B_DAILY_LIMIT:
            print(f"[B2B] Sender {sender.email} at daily limit ({B2B_DAILY_LIMIT}), skipping")
            return

        # Mark as sending before dispatch to prevent double-pick
        lead.status = LeadStatus.sending
        db.commit()

        try:
            tracking_url = f"{app_settings.TRACKING_PIXEL_URL}/pixel/{lead.tracking_id}"
            result_msg = send_email(
                token_json=sender.gmail_token,
                sender=sender.email,
                to=lead.contact_email,
                subject=subject,
                body=body,
                tracking_pixel_url=tracking_url,
            )
            lead.status = LeadStatus.sent
            lead.sent_at = now
            lead.gmail_message_id = result_msg.get("id")
            lead.gmail_thread_id = result_msg.get("threadId")
            db.add(LeadActivity(lead_id=lead.id, action="email_sent", detail=f"Sent to {lead.contact_email}"))
        except Exception as e:
            print(f"[B2B] Send error {lead.id}: {e}")
            lead.status = LeadStatus.failed

        db.commit()

        # Schedule follow-ups as a separate task (survives worker restarts)
        if lead.status == LeadStatus.sent:
            from app.tasks.b2b_leads import schedule_b2b_followups_task
            schedule_b2b_followups_task.delay(str(lead.id))
