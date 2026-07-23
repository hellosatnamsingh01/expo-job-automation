from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "expandimo",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.scraper",
        "app.tasks.matcher",
        "app.tasks.applicator",
        "app.tasks.outreach",
        "app.tasks.followup",
        "app.tasks.scorer",
        "app.tasks.researcher",
        "app.tasks.reply_checker",
        "app.tasks.company_enrichment",
        "app.tasks.b2b_leads",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    # Check every hour which platforms are due — task respects each platform's scrape_frequency_hours
    "scrape-all-platforms": {
        "task": "app.tasks.scraper.scrape_all_platforms_task",
        "schedule": crontab(minute=0),
    },
    # Match new/skipped jobs against all profiles — interval configurable via Settings
    # Default: every 1 hour. Changing profile_match_interval_hours in Settings takes
    # effect after the Celery beat worker is restarted (or use "Match Now" for immediate run).
    "match-unmatched-jobs": {
        "task": "app.tasks.matcher.match_all_unmatched_task",
        "schedule": crontab(minute=0),  # overridden dynamically below if DB setting differs
    },
    # Re-queue ready jobs that have no Application record (recovery for worker restarts)
    "requeue-ready-jobs": {
        "task": "app.tasks.applicator.requeue_ready_jobs_task",
        "schedule": crontab(minute="*/15"),
    },
    # B2B: import leads from Apollo.io daily at 06:00 UTC
    "import-apollo-leads": {
        "task": "app.tasks.b2b_leads.import_apollo_leads_task",
        "schedule": crontab(minute=0, hour=6),
    },
    # B2B: import leads from LinkedIn via Apify (Mon + Thu 07:00 UTC)
    "import-linkedin-leads": {
        "task": "app.tasks.b2b_leads.import_linkedin_leads_task",
        "schedule": crontab(minute=0, hour=7, day_of_week="1,4"),
    },
    # B2B: recovery — queue outreach for scored/approved leads, backfill follow-ups
    "requeue-b2b-leads": {
        "task": "app.tasks.b2b_leads.requeue_b2b_leads_task",
        "schedule": crontab(minute="*/15"),
    },
    # B2B: enrich leads that have no email yet (Hunter lookup), every 30 min
    "enrich-b2b-leads": {
        "task": "app.tasks.b2b_leads.enrich_b2b_leads_task",
        "schedule": crontab(minute="*/30"),
    },
    # B2B: send due follow-up emails every 30 minutes
    "send-b2b-followups": {
        "task": "app.tasks.b2b_leads.send_due_b2b_followups_task",
        "schedule": crontab(minute="*/30"),
    },
    # Send scheduled emails every 5 minutes — sends at most 1 email per tick
    # so emails are naturally spaced ≥2 min apart, preventing Gmail spam flags
    "send-scheduled-emails": {
        "task": "app.tasks.applicator.send_scheduled_applications_task",
        "schedule": crontab(minute="*/2"),
    },
    # Follow-ups are handled inside send_scheduled_applications_task now
    # Keep this as a safety net for older follow-up records
    "send-followups": {
        "task": "app.tasks.followup.process_followups_task",
        "schedule": crontab(minute=30),
    },
    # B2B scheduled emails every 15 minutes
    "send-b2b-emails": {
        "task": "app.tasks.outreach.send_scheduled_b2b_task",
        "schedule": crontab(minute="*/15"),
    },
    # Check Gmail threads for replies every 10 minutes
    "check-replies": {
        "task": "app.tasks.reply_checker.check_replies_task",
        "schedule": crontab(minute="*/10"),
    },
    # Check Gmail inbox for bounce/delivery-failure notifications every 30 minutes
    "check-bounces": {
        "task": "app.tasks.bounce_checker.check_bounces_task",
        "schedule": crontab(minute="*/30"),
    },
    # Enrich missing job descriptions every 2 hours
    "enrich-job-descriptions": {
        "task": "app.tasks.scraper.enrich_job_descriptions_task",
        "schedule": crontab(minute=0, hour="*/2"),
    },
    # Re-research jobs stuck in researching status every 3 hours
    "research-pending-jobs": {
        "task": "app.tasks.researcher.research_all_pending_task",
        "schedule": crontab(minute=30, hour="*/3"),
    },
    # Retry company size enrichment once a day for any jobs still missing it
    "backfill-company-sizes": {
        "task": "app.tasks.company_enrichment.backfill_company_sizes_task",
        "schedule": crontab(minute=0, hour=3),  # 3 AM UTC daily
    },
    # Auto-delete skipped jobs older than configured retention period (twice daily: 02:00 and 14:00 UTC)
    "cleanup-skipped-jobs": {
        "task": "app.tasks.matcher.cleanup_skipped_jobs_task",
        "schedule": crontab(minute=0, hour="2,14"),
    },
}

# Override match interval from DB setting at startup
try:
    from app.db.base import SyncSessionLocal
    from app.models.settings import GlobalSetting
    with SyncSessionLocal() as _db:
        _row = _db.query(GlobalSetting).filter(GlobalSetting.key == "profile_match_interval_hours").first()
        _hours = int(_row.value) if _row and _row.value else 1
    if _hours == 1:
        _match_schedule = crontab(minute=0)
    else:
        _match_schedule = crontab(minute=0, hour=f"*/{_hours}")
    celery_app.conf.beat_schedule["match-unmatched-jobs"]["schedule"] = _match_schedule
except Exception:
    pass  # fall back to default hourly crontab set above
