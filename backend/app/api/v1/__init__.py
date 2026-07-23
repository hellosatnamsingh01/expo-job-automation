from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, profiles, platforms, jobs, applications, leads, templates, settings, track, analytics, email_accounts, activities, alerts

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
router.include_router(platforms.router, prefix="/platforms", tags=["platforms"])
router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
router.include_router(applications.router, prefix="/applications", tags=["applications"])
router.include_router(leads.router, prefix="/leads", tags=["leads"])
router.include_router(templates.router, prefix="/templates", tags=["templates"])
router.include_router(settings.router, prefix="/settings", tags=["settings"])
router.include_router(track.router, prefix="/track", tags=["tracking"])
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
router.include_router(email_accounts.router, prefix="/email-accounts", tags=["email-accounts"])
router.include_router(activities.router, prefix="/activities", tags=["activities"])
router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
