from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
import json

from app.db.base import get_db
from app.models.settings import GlobalSetting
from app.models.user import Permission
from app.core.deps import require_permission

router = APIRouter()

DEFAULT_SETTINGS = {
    "approval_enabled_jobs": "true",
    "approval_enabled_b2b": "true",
    "excluded_countries": "[]",
    "followup_days": "[2, 4, 6]",
    "send_time_start": "09:00",
    "send_time_end": "11:00",
    "blacklisted_companies": "[]",
    "auto_scrape_enabled": "true",
    "auto_apply_enabled": "false",
    "daily_email_limit": "15",
    "min_gap_minutes": "5",
    "profile_match_interval_hours": "1",
    "skipped_job_retention_days": "0",
}


class SettingsUpdate(BaseModel):
    approval_enabled_jobs: Optional[bool] = None
    approval_enabled_b2b: Optional[bool] = None
    excluded_countries: Optional[List[str]] = None
    followup_days: Optional[List[int]] = None
    send_time_start: Optional[str] = None
    send_time_end: Optional[str] = None
    blacklisted_companies: Optional[List[str]] = None
    auto_scrape_enabled: Optional[bool] = None
    auto_apply_enabled: Optional[bool] = None
    daily_email_limit: Optional[int] = None
    min_gap_minutes: Optional[int] = None
    profile_match_interval_hours: Optional[int] = None
    skipped_job_retention_days: Optional[int] = None


async def get_setting(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(GlobalSetting).where(GlobalSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        return setting.value
    return DEFAULT_SETTINGS.get(key, "")


async def set_setting(db: AsyncSession, key: str, value: str):
    result = await db.execute(select(GlobalSetting).where(GlobalSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(GlobalSetting(key=key, value=value))


@router.get("/")
async def get_settings(
    current_user=Depends(require_permission(Permission.manage_settings)),
    db: AsyncSession = Depends(get_db),
):
    out = {}
    for key in DEFAULT_SETTINGS:
        val = await get_setting(db, key)
        try:
            out[key] = json.loads(val)
        except Exception:
            out[key] = val
    return out


@router.get("/api-keys")
async def get_api_keys(
    current_user=Depends(require_permission(Permission.manage_settings)),
    db: AsyncSession = Depends(get_db),
):
    """Return saved API keys (masked for display)."""
    apollo = await get_setting(db, "apollo_api_keys")
    lusha = await get_setting(db, "lusha_api_keys")
    hunter = await get_setting(db, "hunter_api_keys")
    anthropic = await get_setting(db, "anthropic_api_key")
    openai = await get_setting(db, "openai_api_key")
    groq = await get_setting(db, "groq_api_key")
    apify = await get_setting(db, "apify_token")
    google_places = await get_setting(db, "google_places_api_key")
    return {
        "apollo_api_keys": apollo,
        "lusha_api_keys": lusha,
        "hunter_api_keys": hunter,
        "anthropic_api_key": anthropic,
        "openai_api_key": openai,
        "groq_api_key": groq,
        "apify_token": apify,
        "google_places_api_key": google_places,
    }


class ApiKeysUpdate(BaseModel):
    apollo_api_keys: Optional[str] = None
    lusha_api_keys: Optional[str] = None
    hunter_api_keys: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    apify_token: Optional[str] = None
    google_places_api_key: Optional[str] = None


@router.put("/api-keys")
async def update_api_keys(
    data: ApiKeysUpdate,
    current_user=Depends(require_permission(Permission.manage_settings)),
    db: AsyncSession = Depends(get_db),
):
    """Save API keys to DB and reload them into the running config."""
    from app.core.config import settings as app_settings
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        await set_setting(db, key, value)
        # Hot-reload into running settings so worker picks up immediately
        if key == "apollo_api_keys":
            app_settings.APOLLO_API_KEYS = value
        elif key == "lusha_api_keys":
            app_settings.LUSHA_API_KEYS = value
        elif key == "anthropic_api_key":
            app_settings.ANTHROPIC_API_KEY = value
    await db.commit()
    return {"message": "API keys saved"}


@router.get("/hunter-usage")
async def get_hunter_usage(
    current_user=Depends(require_permission(Permission.manage_settings)),
    db: AsyncSession = Depends(get_db),
):
    """Return usage stats for each Hunter.io API key."""
    import httpx as _httpx
    from app.tasks.researcher import _get_hunter_keys, _parse_keys

    raw = await get_setting(db, "hunter_api_keys") or ""
    # Preserve email labels alongside keys
    accounts = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or "your-" in part:
            continue
        if "|" in part:
            email, key = part.split("|", 1)
            accounts.append({"email": email.strip(), "key": key.strip()})
        else:
            accounts.append({"email": "", "key": part.strip()})

    results = []
    for acc in accounts:
        key = acc["key"]
        try:
            r = _httpx.get(
                "https://api.hunter.io/v2/account",
                params={"api_key": key},
                timeout=8,
            )
            data = r.json().get("data", {}) or {}
            searches = (data.get("requests") or {}).get("searches") or {}
            used = searches.get("used", 0)
            available = searches.get("available", 50)
            results.append({
                "email": acc["email"],
                "key_prefix": key[:8] + "...",
                "plan": data.get("plan_name", "free"),
                "used": used,
                "available": available,
                "reset_date": data.get("reset_date"),
                "exhausted": used >= available,
            })
        except Exception:
            results.append({
                "email": acc["email"],
                "key_prefix": key[:8] + "...",
                "plan": "unknown",
                "used": None,
                "available": None,
                "reset_date": None,
                "exhausted": None,
            })

    return {"keys": results}


@router.get("/hasdata-usage")
async def get_hasdata_usage(
    current_user=Depends(require_permission(Permission.manage_settings)),
    db: AsyncSession = Depends(get_db),
):
    """
    Return status for each HasData API key by probing the /scrape/credits endpoint.
    HasData has no credits API — a 403 means exhausted, 400/200 means active.
    """
    import httpx as _httpx
    from sqlalchemy import select as _select
    from app.models.platform import Platform

    result = await db.execute(_select(Platform).where(Platform.name == "Indeed"))
    platform = result.scalar_one_or_none()
    if not platform or not platform.scrape_config:
        return {"keys": []}

    raw_keys = platform.scrape_config.get("api_keys") or []
    keys_info = []
    for i, k in enumerate(raw_keys):
        key = k["key"] if isinstance(k, dict) else k
        email = k.get("email", "") if isinstance(k, dict) else ""
        if not key:
            continue

        try:
            r = _httpx.get(
                "https://api.hasdata.com/scrape/credits",
                headers={"x-api-key": key},
                timeout=8,
            )
            if r.status_code == 403:
                status = "exhausted"
                credits_left = 0
            elif r.status_code in (200, 400):
                # 400 means active but needs a URL param — credits are available
                status = "active"
                data = r.json() if r.status_code == 200 else {}
                credits_left = (
                    data.get("creditsLeft")
                    or data.get("credits")
                    or data.get("balance")
                    or None
                )
            else:
                status = "unknown"
                credits_left = None
        except Exception:
            status = "unknown"
            credits_left = None

        keys_info.append({
            "email": email or f"Key #{i+1}",
            "key_prefix": key[:8] + "...",
            "status": status,
            "credits_left": credits_left,
            "renew_date": k.get("renew_date", "") if isinstance(k, dict) else "",
        })

    return {"keys": keys_info}


@router.get("/apify-usage")
async def get_apify_usage(
    current_user=Depends(require_permission(Permission.manage_settings)),
    db: AsyncSession = Depends(get_db),
):
    """Return status for each Apify key by calling the Apify account API."""
    import httpx as _httpx
    from sqlalchemy import select as _select
    from app.models.platform import Platform

    result = await db.execute(_select(Platform).where(Platform.name == "LinkedIn Jobs"))
    platform = result.scalar_one_or_none()
    if not platform or not platform.scrape_config:
        return {"keys": []}

    raw_keys = platform.scrape_config.get("api_keys") or []
    keys_info = []
    for i, k in enumerate(raw_keys):
        key = k["key"] if isinstance(k, dict) else k
        email = k.get("email", "") if isinstance(k, dict) else ""
        renew_date = k.get("renew_date", "") if isinstance(k, dict) else ""
        if not key:
            continue
        try:
            r = _httpx.get(
                "https://api.apify.com/v2/users/me",
                params={"token": key},
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json().get("data", {})
                plan = data.get("plan", {})
                usage = data.get("limits", {})
                monthly_usage = data.get("monthlyUsage", {})
                status = "active"
                credits_used = monthly_usage.get("actorComputeUnits", None)
                credits_limit = plan.get("monthlyActorComputeUnits", None)
            elif r.status_code in (401, 403):
                status = "exhausted"
                credits_used = None
                credits_limit = None
            else:
                status = "unknown"
                credits_used = None
                credits_limit = None
        except Exception:
            status = "unknown"
            credits_used = None
            credits_limit = None

        keys_info.append({
            "email": email or f"Key #{i+1}",
            "key_prefix": key[:16] + "...",
            "status": status,
            "credits_used": credits_used,
            "credits_limit": credits_limit,
            "renew_date": renew_date,
        })

    return {"keys": keys_info}


@router.post("/research-now")
async def trigger_research_now(
    current_user=Depends(require_permission(Permission.manage_settings)),
):
    """Trigger immediate research for all pending jobs."""
    from app.tasks.researcher import research_all_pending_task
    research_all_pending_task.delay()
    return {"message": "Research triggered for all pending jobs"}


@router.post("/match-now")
async def trigger_match_now(
    current_user=Depends(require_permission(Permission.manage_settings)),
):
    """Trigger immediate profile matching for all new/skipped jobs."""
    from app.tasks.matcher import match_all_unmatched_task
    match_all_unmatched_task.delay()
    return {"message": "Profile matching triggered for all unmatched jobs"}


@router.put("/")
async def update_settings(
    data: SettingsUpdate,
    current_user=Depends(require_permission(Permission.manage_settings)),
    db: AsyncSession = Depends(get_db),
):
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        if isinstance(value, (list, dict)):
            await set_setting(db, key, json.dumps(value))
        elif isinstance(value, bool):
            await set_setting(db, key, str(value).lower())
        else:
            await set_setting(db, key, str(value))
    await db.commit()
    return {"message": "Settings updated"}


@router.post("/cleanup-skipped-now")
async def trigger_cleanup_skipped_now(
    current_user=Depends(require_permission(Permission.manage_settings)),
):
    """Immediately delete skipped jobs older than the configured retention period."""
    from app.tasks.matcher import cleanup_skipped_jobs_task
    cleanup_skipped_jobs_task.delay()
    return {"message": "Skipped job cleanup triggered"}
