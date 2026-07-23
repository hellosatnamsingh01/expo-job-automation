from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal


@celery_app.task(name="app.tasks.scorer.score_lead_task")
def score_lead_task(lead_id: str):
    import uuid
    from app.models.lead import Lead, LeadActivity
    from app.services.ai_service import score_lead

    with SyncSessionLocal() as db:
        lead = db.query(Lead).filter(Lead.id == uuid.UUID(lead_id)).first()
        if not lead:
            return

        scored = score_lead(
            company_name=lead.company_name,
            industry=lead.industry or "",
            country=lead.country or "",
            company_size=lead.company_size or "",
            domain=lead.domain or "",
        )

        lead.score = scored.get("score", 50)
        lead.score_breakdown = scored.get("breakdown", {})
        db.add(LeadActivity(
            lead_id=lead.id,
            action="scored",
            detail=f"AI score: {lead.score}/100 — {scored.get('reason', '')}",
        ))
        db.commit()
