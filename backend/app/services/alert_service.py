"""
Thin helper to write SystemAlert rows from anywhere (tasks, endpoints).
Always uses the sync session so it works inside Celery tasks.
"""
from app.models.alert import SystemAlert, AlertType, AlertSeverity
from app.db.base import SyncSessionLocal
from datetime import datetime, timedelta


# How long before the same alert can fire again (dedup window)
_DEDUP_HOURS: dict[AlertType, int] = {
    AlertType.key_exhausted:  2,   # noisy — same key exhaustion, suppress for 2h
    AlertType.key_rotated:    2,   # noisy — key rotation, suppress for 2h
    AlertType.platform_ok:    6,   # success noise — once per 6h per platform
    AlertType.platform_error: 1,
    AlertType.email_error:    0,   # always show email errors
    AlertType.reply_received: 0,   # always show replies
    AlertType.b2b_reply:      0,
    AlertType.lead_imported:  1,
    AlertType.enrich_done:    1,
    AlertType.system:         1,
}


def create_alert(
    type: AlertType,
    title: str,
    message: str = "",
    source: str = "",
    severity: AlertSeverity = AlertSeverity.info,
) -> None:
    try:
        with SyncSessionLocal() as db:
            dedup_hours = _DEDUP_HOURS.get(type, 1)
            if dedup_hours > 0:
                cutoff = datetime.utcnow() - timedelta(hours=dedup_hours)
                existing = db.query(SystemAlert).filter(
                    SystemAlert.type == type,
                    SystemAlert.title == title,
                    SystemAlert.created_at >= cutoff,
                ).first()
                if existing:
                    return  # duplicate — skip

            db.add(SystemAlert(
                id=__import__("uuid").uuid4().__str__(),
                type=type,
                severity=severity,
                title=title,
                message=message,
                source=source,
            ))
            db.commit()
    except Exception as e:
        print(f"[Alert] Failed to write alert: {e}")
