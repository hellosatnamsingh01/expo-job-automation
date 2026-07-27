"""
Daily task: check API keys whose renew_date has passed and probe the provider to
confirm credits are back. Sends a key_renewed alert if confirmed active, or a
key_error alert if the key is still exhausted after its renewal date.
"""
from datetime import datetime, date
import httpx

from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
from app.models.platform import Platform
from app.models.alert import AlertType, AlertSeverity
from app.services.alert_service import create_alert


def _probe_hasdata(key: str) -> bool:
    """Return True if the HasData key has credits available."""
    try:
        r = httpx.get(
            "https://api.hasdata.com/scrape/credits",
            headers={"x-api-key": key},
            timeout=8,
        )
        return r.status_code in (200, 400)  # 400 = active but missing URL param
    except Exception:
        return False


def _probe_apify(key: str) -> bool:
    """Return True if the Apify key is valid and active."""
    try:
        r = httpx.get(
            "https://api.apify.com/v2/users/me",
            params={"token": key},
            timeout=8,
        )
        return r.status_code == 200
    except Exception:
        return False


@celery_app.task(name="app.tasks.key_renewal.check_key_renewals_task")
def check_key_renewals_task():
    """Check all platform API keys whose renew_date is today or past."""
    today = date.today()

    with SyncSessionLocal() as db:
        platforms = db.query(Platform).all()

    for platform in platforms:
        if not platform.scrape_config:
            continue

        raw_keys = platform.scrape_config.get("api_keys") or []
        is_linkedin = platform.name == "LinkedIn Jobs"
        is_indeed = platform.name == "Indeed"

        if not is_linkedin and not is_indeed:
            continue

        for k in raw_keys:
            if not isinstance(k, dict):
                continue

            renew_date_str = k.get("renew_date", "")
            if not renew_date_str:
                continue

            try:
                renew_date = datetime.strptime(renew_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            if renew_date > today:
                continue  # not due yet

            key = k.get("key", "")
            email = k.get("email") or f"Key ...{key[-6:]}" if key else "Unknown"
            label = f"{platform.name} — {email}"

            if is_indeed:
                active = _probe_hasdata(key)
            else:
                active = _probe_apify(key)

            if active:
                create_alert(
                    type=AlertType.key_renewed,
                    title=f"{label} renewed and active",
                    message=(
                        f"Renewal date {renew_date_str} has passed. "
                        f"Live API probe confirms credits are available again."
                    ),
                    source=platform.name,
                    severity=AlertSeverity.info,
                )
                print(f"[KeyRenewal] {label} confirmed active after renewal date {renew_date_str}")
            else:
                create_alert(
                    type=AlertType.key_error,
                    title=f"{label} still exhausted after renewal date",
                    message=(
                        f"Renewal date {renew_date_str} has passed but the live API probe "
                        f"still returns exhausted/unauthorised. Check the provider account."
                    ),
                    source=platform.name,
                    severity=AlertSeverity.warning,
                )
                print(f"[KeyRenewal] {label} STILL exhausted after renewal date {renew_date_str}")
