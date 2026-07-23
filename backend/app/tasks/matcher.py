from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal


@celery_app.task(name="app.tasks.matcher.match_all_unmatched_task")
def match_all_unmatched_task():
    """Re-evaluate all unmatched/skipped jobs against all active profiles."""
    import redis as _redis
    from app.core.config import settings as _cfg
    from app.models.job import Job, JobStatus

    # Don't pile on when queue is already busy
    try:
        _r = _redis.from_url(_cfg.REDIS_URL)
        depth = _r.llen("celery")
        if depth > 200:
            print(f"[Matcher] Queue depth {depth} too high — skipping full re-match")
            return
    except Exception:
        pass

    with SyncSessionLocal() as db:
        jobs = db.query(Job).filter(
            Job.status.in_([JobStatus.new, JobStatus.skipped]),
        ).limit(100).all()
        ids = [str(j.id) for j in jobs]
    for i, jid in enumerate(ids):
        match_job_task.apply_async(args=[jid], countdown=i * 1)


def _extract_skills_for_job(job_text: str, all_skills: list[str]) -> list[str]:
    """Return up to 4 primary skills that appear in the job text."""
    found = [s for s in all_skills if s.lower() in job_text]
    return found[:4]


def _infer_job_industry(title: str, description: str) -> str:
    text = (title + " " + description[:500]).lower()
    if any(k in text for k in ["shopify", "woocommerce", "ecommerce", "e-commerce", "magento", "retail", "online store"]):
        return "E-Commerce"
    if any(k in text for k in ["health", "medical", "medtech", "clinic", "pharma", "patient", "ehr", "emr", "hospital"]):
        return "Healthcare / MedTech"
    if any(k in text for k in ["real estate", "property", "realty", "proptech", "mortgage", "rental"]):
        return "Real Estate / PropTech"
    if any(k in text for k in ["fintech", "banking", "payments", "trading", "insurance", "lending", "crypto", "blockchain"]):
        return "FinTech"
    if any(k in text for k in ["edtech", "education", "learning", "e-learning", "lms", "course", "tutoring"]):
        return "EdTech"
    if any(k in text for k in ["game", "gaming", "unity", "unreal", "game engine"]):
        return "Gaming"
    if any(k in text for k in ["marketing", "seo", "growth", "analytics", "crm", "ad tech", "adtech"]):
        return "Marketing Tech"
    if any(k in text for k in ["devops", "cloud", "aws", "azure", "infrastructure", "kubernetes", "docker", "platform engineer"]):
        return "Cloud / DevOps"
    if any(k in text for k in ["mobile", "ios", "android", "flutter", "react native"]):
        return "Mobile"
    if any(k in text for k in ["cybersecurity", "security", "pentest", "soc ", "siem", "devsecops"]):
        return "Cybersecurity"
    if any(k in text for k in ["ai ", "machine learning", "ml ", "llm", "data science", "nlp", "computer vision"]):
        return "AI / ML"
    return "SaaS / Tech"


_NON_ENGLISH_PATTERNS = [
    # Common non-English words that appear in job titles/descriptions
    "nous recherchons", "nous sommes", "descripción", "descripcion", "estamos buscando",
    "wir suchen", "wir sind", "stellenbeschreibung", "cerchiamo", "stiamo cercendo",
    "buscamos", "oferta de empleo", "procuramos", "estamos à procura",
    "zoeken wij", "wij zoeken", "szukamy", "hledáme", "hledame",
    "işe alıyoruz", "ise aliyoruz", "мы ищем", "مطلوب", "नौकरी",
]

def _is_non_english(text: str) -> bool:
    """Return True if the job text appears to be non-English."""
    lower = text.lower()
    return any(pat in lower for pat in _NON_ENGLISH_PATTERNS)


# Minimum skill matches required for a job to be assigned to a profile
MIN_MATCH_SCORE = 1


@celery_app.task(name="app.tasks.matcher.match_job_task")
def match_job_task(job_id: str):
    import uuid, json
    from app.models.job import Job, JobStatus, JobContact
    from app.models.profile import Profile, ProfileSkill, SkillType
    from app.models.settings import GlobalSetting

    with SyncSessionLocal() as db:
        job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if not job:
            return

        exc_setting = db.query(GlobalSetting).filter(GlobalSetting.key == "excluded_countries").first()
        excluded = json.loads(exc_setting.value) if exc_setting and exc_setting.value else []
        if job.country and job.country in excluded:
            job.status = JobStatus.skipped
            # Still tag skills even for skipped/excluded jobs
            all_skills = [s.skill for s in db.query(ProfileSkill).filter(ProfileSkill.skill_type == SkillType.primary).all()]
            skills_text = " ".join(job.required_skills) if job.required_skills else ""
            job_text = f"{job.title} {job.job_description or ''} {skills_text}".lower()
            job.required_skills = _extract_skills_for_job(job_text, all_skills)
            db.commit()
            return

        skills_text = " ".join(job.required_skills) if job.required_skills else ""
        job_text = f"{job.title} {job.job_description or ''} {skills_text}".lower()

        # Skip non-English jobs
        if _is_non_english(job_text):
            all_skills = [s.skill for s in db.query(ProfileSkill).filter(ProfileSkill.skill_type == SkillType.primary).all()]
            job.required_skills = _extract_skills_for_job(job_text, all_skills)
            job.status = JobStatus.skipped
            db.commit()
            print(f"[Matcher] Skipped non-English job: {job.title}")
            return

        profiles = db.query(Profile).filter(Profile.is_active == True).all()
        best_profile = None
        best_score = 0
        best_skills: list[str] = []

        for profile in profiles:
            primary_skills = [
                s.skill
                for s in db.query(ProfileSkill).filter(
                    ProfileSkill.profile_id == profile.id,
                    ProfileSkill.skill_type == SkillType.primary
                ).all()
            ]
            skill_matches = [s for s in primary_skills if s.lower() in job_text]
            if len(skill_matches) > best_score:
                best_score = len(skill_matches)
                best_profile = profile
                best_skills = skill_matches

        if not job.industry:
            job.industry = _infer_job_industry(job.title, job.job_description or "")

        if best_profile and best_score >= MIN_MATCH_SCORE:
            job.matched_profile_id = best_profile.id
            job.required_skills = best_skills[:4]
            has_contact = db.query(JobContact).filter(JobContact.job_id == job.id).first()
            job.status = JobStatus.ready if has_contact else JobStatus.researching
            db.commit()

            if job.status == JobStatus.researching:
                from app.tasks.researcher import research_job_task
                research_job_task.delay(str(job.id))
            elif job.status == JobStatus.ready:
                from app.tasks.applicator import apply_job_task
                apply_job_task.delay(str(job.id))
        else:
            # No profile matched — tag skills from all profiles and mark skipped
            all_skills = [s.skill for s in db.query(ProfileSkill).filter(ProfileSkill.skill_type == SkillType.primary).all()]
            job.required_skills = _extract_skills_for_job(job_text, all_skills)
            if not job.industry:
                job.industry = _infer_job_industry(job.title, job.job_description or "")
            job.status = JobStatus.skipped
            db.commit()


@celery_app.task(name="app.tasks.matcher.cleanup_skipped_jobs_task")
def cleanup_skipped_jobs_task():
    """Delete skipped jobs older than the configured retention period. Runs twice daily."""
    from datetime import datetime, timedelta
    from sqlalchemy import or_
    from app.models.job import Job, JobStatus
    from app.models.settings import GlobalSetting

    with SyncSessionLocal() as db:
        row = db.query(GlobalSetting).filter(GlobalSetting.key == "skipped_job_retention_days").first()
        days = int(row.value) if row and row.value else 0
        if days <= 0:
            print("[Cleanup] Skipped job retention disabled (days=0), nothing to do")
            return

        cutoff = datetime.utcnow() - timedelta(days=days)
        print(f"[Cleanup] Deleting skipped jobs older than {days} days (before {cutoff.date()})")

        # Use scraped_at if available, fall back to created_at
        deleted = (
            db.query(Job)
            .filter(
                Job.status == JobStatus.skipped,
                or_(
                    Job.scraped_at < cutoff,
                    Job.scraped_at.is_(None),  # manually added with no scraped_at → use created_at
                ),
                Job.created_at < cutoff,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        print(f"[Cleanup] Deleted {deleted} skipped jobs older than {days} days")
