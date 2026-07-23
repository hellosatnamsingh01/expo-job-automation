from datetime import datetime, timedelta
import pytz
import holidays
import random


COUNTRY_TIMEZONE_MAP = {
    "US": "America/New_York",
    "USA": "America/New_York",
    "United States": "America/New_York",
    "UK": "Europe/London",
    "United Kingdom": "Europe/London",
    "GB": "Europe/London",
    "Canada": "America/Toronto",
    "CA": "America/Toronto",
    "Australia": "Australia/Sydney",
    "AU": "Australia/Sydney",
    "Germany": "Europe/Berlin",
    "DE": "Europe/Berlin",
    "France": "Europe/Paris",
    "FR": "Europe/Paris",
    "Netherlands": "Europe/Amsterdam",
    "NL": "Europe/Amsterdam",
    "India": "Asia/Kolkata",
    "IN": "Asia/Kolkata",
    "Singapore": "Asia/Singapore",
    "SG": "Asia/Singapore",
    "UAE": "Asia/Dubai",
    "AE": "Asia/Dubai",
    "Pakistan": "Asia/Karachi",
    "PK": "Asia/Karachi",
}

DEFAULT_SEND_HOUR = 9
DEFAULT_SEND_MINUTE = 30
_DEFAULT_DAILY_LIMIT = 10  # Conservative — Gmail blocks bursts; 10/day keeps accounts safe
_DEFAULT_MIN_GAP = 5


def _get_limits():
    """Read daily_email_limit and min_gap_minutes from DB, fall back to defaults."""
    try:
        from app.db.base import SyncSessionLocal
        from app.models.settings import GlobalSetting
        with SyncSessionLocal() as db:
            dl = db.query(GlobalSetting).filter(GlobalSetting.key == "daily_email_limit").first()
            mg = db.query(GlobalSetting).filter(GlobalSetting.key == "min_gap_minutes").first()
            daily_limit = int(dl.value) if dl and dl.value else _DEFAULT_DAILY_LIMIT
            min_gap = int(mg.value) if mg and mg.value else _DEFAULT_MIN_GAP
            return daily_limit, min_gap
    except Exception:
        return _DEFAULT_DAILY_LIMIT, _DEFAULT_MIN_GAP


def get_send_window_from_db():
    """Read send_time_start / send_time_end from GlobalSettings, fall back to defaults."""
    try:
        from app.db.base import SyncSessionLocal
        from app.models.settings import GlobalSetting
        with SyncSessionLocal() as db:
            start = db.query(GlobalSetting).filter(GlobalSetting.key == "send_time_start").first()
            sh, sm = DEFAULT_SEND_HOUR, DEFAULT_SEND_MINUTE
            if start and start.value:
                parts = start.value.split(":")
                sh, sm = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            return sh, sm
    except Exception:
        return DEFAULT_SEND_HOUR, DEFAULT_SEND_MINUTE


def get_timezone_for_country(country: str) -> str:
    return COUNTRY_TIMEZONE_MAP.get(country, "UTC")


def is_business_day(dt: datetime, country_code: str = None) -> bool:
    if dt.weekday() >= 5:
        return False
    if country_code:
        try:
            country_holidays = holidays.country_holidays(country_code, years=dt.year)
            if dt.date() in country_holidays:
                return False
        except Exception:
            pass
    return True


def next_business_day(dt: datetime, country_code: str = None) -> datetime:
    next_day = dt + timedelta(days=1)
    while not is_business_day(next_day, country_code):
        next_day += timedelta(days=1)
    return next_day


def _count_emails_today(sender_email: str, date_utc: datetime) -> int:
    """Count how many emails already scheduled/sent from this sender on the given UTC day."""
    try:
        from app.db.base import SyncSessionLocal
        from app.models.application import Application, ApplicationStatus
        from sqlalchemy import func
        day_start = date_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        with SyncSessionLocal() as db:
            # Count by sent_at (actual delivery time) — not scheduled_at.
            # This correctly limits Gmail sends regardless of when they were scheduled.
            sent = db.query(func.count(Application.id)).filter(
                Application.sender_email == sender_email,
                Application.sent_at >= day_start,
                Application.sent_at < day_end,
                Application.status.in_([
                    ApplicationStatus.sent, ApplicationStatus.sending,
                ]),
            ).scalar() or 0
            # Also count emails scheduled for future slots on this day (not yet sent)
            scheduled = db.query(func.count(Application.id)).filter(
                Application.sender_email == sender_email,
                Application.scheduled_at >= day_start,
                Application.scheduled_at < day_end,
                Application.sent_at.is_(None),
                Application.status.in_([
                    ApplicationStatus.scheduled, ApplicationStatus.pending_approval,
                ]),
            ).scalar() or 0
            return sent + scheduled
    except Exception:
        return 0


def _latest_scheduled_time(sender_email: str) -> datetime | None:
    """Return the latest scheduled_at for this specific sender across all future emails."""
    try:
        from app.db.base import SyncSessionLocal
        from app.models.application import Application, ApplicationStatus
        from sqlalchemy import func
        with SyncSessionLocal() as db:
            result = db.query(func.max(Application.scheduled_at)).filter(
                Application.sender_email == sender_email,
                Application.scheduled_at >= datetime.utcnow(),
                Application.status.in_([ApplicationStatus.scheduled, ApplicationStatus.pending_approval]),
                Application.sent_at.is_(None),
            ).scalar()
            return result
    except Exception:
        return None


def get_send_datetime(country: str, sender_email: str = None, send_hour: int = None, send_minute: int = None, after: datetime = None) -> datetime:
    """
    Returns the next available send datetime in UTC for the given country.
    Enforces:
    - Max DAILY_LIMIT emails per sender per day
    - Min MIN_GAP_MINUTES gap between consecutive emails from same sender
    """
    if send_hour is None or send_minute is None:
        send_hour, send_minute = get_send_window_from_db()

    tz_name = get_timezone_for_country(country)
    tz = pytz.timezone(tz_name)
    now_utc = datetime.utcnow()
    now_local = datetime.now(tz)

    # Determine base send time (today or next business day)
    send_today = now_local.replace(hour=send_hour, minute=send_minute, second=0, microsecond=0)
    if send_today > now_local and is_business_day(send_today, country[:2].upper()):
        base_local = send_today
    else:
        next_bd = next_business_day(now_local, country[:2].upper())
        base_local = next_bd.replace(hour=send_hour, minute=send_minute, second=0, microsecond=0)
        base_local = tz.localize(base_local.replace(tzinfo=None))

    base_utc = base_local.astimezone(pytz.UTC).replace(tzinfo=None)

    daily_limit, min_gap = _get_limits()
    candidate_utc = base_utc

    # Each sender has a fully independent schedule — other senders don't affect this one.
    # Find this sender's latest already-scheduled slot and start after it.
    sender_reference = after
    if sender_email:
        sender_latest = _latest_scheduled_time(sender_email)
        if sender_latest and (sender_reference is None or sender_latest > sender_reference):
            sender_reference = sender_latest

    if sender_reference:
        jitter = random.randint(1, 3)
        after_sender = sender_reference + timedelta(minutes=min_gap + jitter)
        if after_sender > candidate_utc:
            candidate_utc = after_sender

    if not sender_email:
        return candidate_utc

    # Roll to next business day if daily limit reached
    max_attempts = 30
    attempts = 0
    while attempts < max_attempts:
        count_today = _count_emails_today(sender_email, candidate_utc)
        if count_today < daily_limit:
            break
        candidate_local = candidate_utc.replace(tzinfo=pytz.UTC).astimezone(tz)
        next_bd = next_business_day(candidate_local, country[:2].upper())
        candidate_local = next_bd.replace(hour=send_hour, minute=send_minute, second=0, microsecond=0)
        candidate_local = tz.localize(candidate_local.replace(tzinfo=None))
        candidate_utc = candidate_local.astimezone(pytz.UTC).replace(tzinfo=None)
        attempts += 1

    return candidate_utc


def get_followup_datetime(sent_at: datetime, followup_days: int, country: str, sender_email: str = None, after: datetime = None) -> datetime:
    """
    Calculate follow-up send time: exactly N business days after sent_at.

    Rules:
    - The TARGET DATE is fixed (sent_at + N business days). It must not change.
    - Within that day, find the next free slot (min_gap after the latest scheduled email).
    - If the day is already full (daily limit) or all slots are past 17:00 local, move
      to the NEXT business day at DEFAULT_SEND_HOUR — NOT back to the same day as F1/F2.
    - This guarantees F1, F2, F3 always land on different calendar days.
    """
    tz_name = get_timezone_for_country(country)
    tz = pytz.timezone(tz_name)
    country_code = country[:2].upper()
    BUSINESS_END_HOUR = 17  # don't schedule after 5 PM local

    # Step 1: compute the target date (N business days from sent_at)
    current = pytz.UTC.localize(sent_at).astimezone(tz)
    business_days_added = 0
    while business_days_added < followup_days:
        current += timedelta(days=1)
        if is_business_day(current, country_code):
            business_days_added += 1

    target_date = current.date()
    daily_limit, min_gap = _get_limits()

    # Step 2: find the earliest free slot on (or after) the target date (per-sender only)
    reference = after
    if sender_email:
        sender_latest = _latest_scheduled_time(sender_email)
        if sender_latest and (reference is None or sender_latest > reference):
            reference = sender_latest

    # Start from the target date at DEFAULT_SEND_HOUR
    candidate_local = tz.localize(datetime(
        target_date.year, target_date.month, target_date.day,
        DEFAULT_SEND_HOUR, DEFAULT_SEND_MINUTE, 0
    ))
    candidate_utc = candidate_local.astimezone(pytz.UTC).replace(tzinfo=None)

    # Push past the reference (gap from last scheduled email)
    if reference:
        jitter = random.randint(1, 3)
        after_ref = reference + timedelta(minutes=min_gap + jitter)
        if after_ref > candidate_utc:
            candidate_utc = after_ref

    # Step 3: if candidate is past business hours on its day, or daily limit full,
    # roll to the next business day — preserving the minimum N-days-after constraint
    max_attempts = 30
    for _ in range(max_attempts):
        local_candidate = candidate_utc.replace(tzinfo=pytz.UTC).astimezone(tz)
        past_end = local_candidate.hour >= BUSINESS_END_HOUR

        daily_full = False
        if sender_email:
            daily_full = _count_emails_today(sender_email, candidate_utc) >= daily_limit

        if not past_end and not daily_full:
            break

        # Move to next business day at send hour
        next_bd = next_business_day(local_candidate, country_code)
        candidate_local = tz.localize(datetime(
            next_bd.year, next_bd.month, next_bd.day,
            DEFAULT_SEND_HOUR, DEFAULT_SEND_MINUTE, 0
        ))
        candidate_utc = candidate_local.astimezone(pytz.UTC).replace(tzinfo=None)

        # Re-apply gap from reference on the new day
        if reference:
            jitter = random.randint(1, 3)
            after_ref = reference + timedelta(minutes=min_gap + jitter)
            # Only apply gap if reference is on the same day
            ref_local = reference.replace(tzinfo=pytz.UTC).astimezone(tz) if reference.tzinfo else reference
            if ref_local.date() == next_bd.date() and after_ref > candidate_utc:
                candidate_utc = after_ref

    return candidate_utc
