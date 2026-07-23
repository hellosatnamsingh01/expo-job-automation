from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
import httpx
import re
import urllib.parse


def _parse_keys(raw: str) -> list[str]:
    """Parse 'email|key,email|key' or plain 'key,key' format — returns just the keys."""
    keys = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or "your-" in part:
            continue
        # Support both "email|key" and plain "key"
        key = part.split("|")[-1].strip()
        if key:
            keys.append(key)
    return keys


def _get_apollo_keys() -> list[str]:
    from app.core.config import settings
    from app.db.base import SyncSessionLocal
    from app.models.settings import GlobalSetting
    # Prefer DB-stored keys (set via UI) over .env
    with SyncSessionLocal() as db:
        row = db.query(GlobalSetting).filter(GlobalSetting.key == "apollo_api_keys").first()
        if row and row.value:
            keys = _parse_keys(row.value)
            if keys:
                return keys
    # Fallback to .env
    keys = _parse_keys(settings.APOLLO_API_KEYS or "")
    if not keys and settings.APOLLO_API_KEY and "your-" not in (settings.APOLLO_API_KEY or ""):
        keys.append(settings.APOLLO_API_KEY)
    return keys


def _get_lusha_keys() -> list[str]:
    from app.core.config import settings
    from app.db.base import SyncSessionLocal
    from app.models.settings import GlobalSetting
    with SyncSessionLocal() as db:
        row = db.query(GlobalSetting).filter(GlobalSetting.key == "lusha_api_keys").first()
        if row and row.value:
            keys = _parse_keys(row.value)
            if keys:
                return keys
    keys = _parse_keys(settings.LUSHA_API_KEYS or "")
    if not keys and settings.LUCA_API_KEY and "your-" not in (settings.LUCA_API_KEY or ""):
        keys.append(settings.LUCA_API_KEY)
    return keys


def _apollo_titles_for_size(company_size: int) -> list[str]:
    """Return Apollo person_titles priority list based on company size."""
    if company_size > 50:
        return [
            "recruiter", "talent acquisition", "talent acquisition manager",
            "hiring manager", "hr manager", "hr director", "people operations",
            "cto", "vp engineering", "engineering manager", "head of engineering",
            "ceo", "co-founder", "founder",
        ]
    else:
        # Small company — no dedicated HR, go straight to decision makers
        return [
            "ceo", "co-founder", "founder", "owner", "managing director",
            "cto", "vp engineering", "head of engineering", "engineering manager",
            "hr", "recruiter", "people operations",
        ]


def _parse_size_range(size_str: str) -> int:
    """Parse company size string like '1-10', '51-200', '200+' to an integer (lower bound)."""
    if not size_str:
        return 0
    try:
        return int(str(size_str).split("-")[0].replace("+", "").strip())
    except Exception:
        return 0


def _search_apollo(company_name: str, job_title: str = "", company_size: int = 0) -> dict | None:
    """Try all Apollo keys in rotation until one returns a result.
    Uses size-based title priority: small companies → CEO/Founder first, large → HR/Recruiter first.
    """
    keys = _get_apollo_keys()
    if not keys:
        return None

    titles = _apollo_titles_for_size(company_size)
    print(f"[Apollo] Searching {company_name} (size={company_size}) — targeting: {titles[:3]}...")

    for key in keys:
        try:
            resp = httpx.post(
                "https://api.apollo.io/v1/mixed_people/search",
                headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
                json={
                    "api_key": key,
                    "q_organization_name": company_name,
                    "person_titles": titles,
                    "page": 1,
                    "per_page": 5,
                },
                timeout=15,
            )
            if resp.status_code == 401:
                print(f"[Apollo] Key invalid/exhausted: {key[:12]}...")
                continue
            people = resp.json().get("people", [])
            if people:
                # Pick best person by title priority
                def _priority(p):
                    pos = (p.get("title") or "").lower()
                    for i, t in enumerate(titles):
                        if t in pos:
                            return i
                    return 99

                people.sort(key=_priority)
                p = people[0]
                email = p.get("email") or ""
                if not email or "@" not in email:
                    email = _apollo_reveal_email(key, p.get("id", ""))
                print(f"[Apollo] Best contact: {p.get('name')} — {p.get('title')}")
                return {
                    "name": p.get("name"),
                    "title": p.get("title"),
                    "email": email or None,
                    "phone": (p.get("phone_numbers") or [{}])[0].get("sanitized_number") if p.get("phone_numbers") else None,
                    "linkedin_url": p.get("linkedin_url"),
                    "source": "apollo",
                }
        except Exception as e:
            print(f"[Apollo] Error with key {key[:12]}...: {e}")

    return None


def _get_company_size(company_name: str) -> int | None:
    """Get company employee count: use Hunter to find domain, then Apollo org enrich."""
    # Step 1: get domain from Hunter
    domain = None
    hunter_keys = _get_hunter_keys()
    for key in hunter_keys:
        try:
            r = httpx.get(
                "https://api.hunter.io/v2/domain-search",
                params={"company": company_name, "api_key": key, "limit": 1},
                timeout=10,
            )
            if r.status_code == 429:
                break  # All keys likely rate-limited — bail immediately
            if r.status_code == 200:
                domain = r.json().get("data", {}).get("domain")
                if domain:
                    break
        except Exception:
            pass

    if not domain:
        return None

    # Step 2: get employee count from Apollo org enrich
    apollo_keys = _get_apollo_keys()
    for key in apollo_keys:
        try:
            r = httpx.post(
                "https://api.apollo.io/v1/organizations/enrich",
                headers={"Content-Type": "application/json", "X-Api-Key": key},
                json={"domain": domain},
                timeout=10,
            )
            if r.status_code == 200:
                org = r.json().get("organization", {})
                size = org.get("estimated_num_employees")
                if size:
                    return int(size)
        except Exception as e:
            print(f"[CompanySize] Apollo enrich error: {e}")

    return None


def _apollo_reveal_email(api_key: str, person_id: str) -> str | None:
    """Reveal Apollo email via the enrich endpoint (costs 1 credit)."""
    if not person_id:
        return None
    try:
        resp = httpx.post(
            "https://api.apollo.io/v1/people/match",
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
            json={"api_key": api_key, "id": person_id, "reveal_personal_emails": False},
            timeout=15,
        )
        person = resp.json().get("person") or {}
        return person.get("email")
    except Exception:
        return None


def _search_lusha(company_name: str, contact_name: str = "") -> dict | None:
    """Try all Lusha keys in rotation until one returns a result."""
    keys = _get_lusha_keys()
    if not keys:
        return None

    for key in keys:
        try:
            params = {"company": company_name}
            if contact_name:
                parts = contact_name.split()
                if len(parts) >= 2:
                    params["firstName"] = parts[0]
                    params["lastName"] = parts[-1]

            resp = httpx.get(
                "https://api.lusha.com/v2/person",
                headers={"api_key": key},
                params=params,
                timeout=15,
            )
            if resp.status_code in (401, 403):
                print(f"[Lusha] Key invalid/exhausted: {key[:12]}...")
                continue
            data = resp.json().get("data") or {}
            contacts = data.get("contacts") or []
            if not contacts:
                # Some Lusha plans return data directly
                if data.get("emailAddresses"):
                    contacts = [data]
            if contacts:
                c = contacts[0]
                email = (c.get("emailAddresses") or [{}])[0].get("value")
                phone = (c.get("phoneNumbers") or [{}])[0].get("localizedNumber")
                first = c.get("firstName", "")
                last = c.get("lastName", "")
                name = f"{first} {last}".strip() or None
                linkedin = c.get("linkedinUrl") or None
                return {
                    "name": name,
                    "title": c.get("jobTitle"),
                    "email": email,
                    "phone": phone,
                    "linkedin_url": linkedin,
                    "source": "lusha",
                }
        except Exception as e:
            print(f"[Lusha] Error with key {key[:12]}...: {e}")

    return None


def _get_hunter_keys() -> list[str]:
    from app.db.base import SyncSessionLocal
    from app.models.settings import GlobalSetting
    with SyncSessionLocal() as db:
        row = db.query(GlobalSetting).filter(GlobalSetting.key == "hunter_api_keys").first()
        if row and row.value:
            keys = _parse_keys(row.value)
            if keys:
                return keys
    return []


# Hunter department values that are relevant for tech hiring
_ALLOWED_DEPARTMENTS = {"executive", "it", "management", "hr", "engineering", "product", "operations"}
# Titles that indicate wrong department — hard exclude regardless of department field
_EXCLUDED_TITLE_KEYWORDS = [
    "sales", "account executive", "account manager", "business development",
    "finance", "accountant", "controller", "cfo", "treasurer",
    "marketing", "seo", "growth hacker", "content", "brand",
    "legal", "counsel", "attorney", "compliance",
    "pr ", "public relations", "communications",
    "customer success", "customer support", "support agent",
    "supply chain", "logistics", "procurement",
    "data analyst", "data scientist",  # not hiring for dev roles
]


def _derive_role_type(job_title: str) -> str:
    """Classify job title into a role type used to pick the right contact."""
    t = (job_title or "").lower()
    if any(k in t for k in ["shopify", "woocommerce", "magento", "ecommerce", "e-commerce", "bigcommerce"]):
        return "ecommerce"
    if any(k in t for k in ["mobile", "ios", "android", "flutter", "react native", "swift", "kotlin"]):
        return "mobile"
    if any(k in t for k in ["devops", "cloud", "aws", "azure", "gcp", "kubernetes", "platform engineer", "sre", "infrastructure"]):
        return "devops"
    if any(k in t for k in ["wordpress", "drupal", "cms"]):
        return "cms"
    if any(k in t for k in ["ai", "machine learning", "ml ", "data engineer", "nlp", "llm"]):
        return "ai_ml"
    return "fullstack"  # default: full stack / backend / frontend


def _build_title_priority(role_type: str, company_size: int) -> list[str]:
    """
    Return ordered list of target titles.
    Order = who is most likely to be the actual hiring decision-maker for this role.
    Small companies (≤15): founder/CTO makes all hiring decisions directly.
    Mid companies (16-100): engineering manager or head of eng.
    Large companies (101-500): VP Engineering + technical recruiter.
    Enterprise (500+): technical/engineering recruiter specifically.
    """
    role_specific = {
        "ecommerce": ["head of ecommerce", "ecommerce manager", "ecommerce director", "ecommerce lead",
                      "shopify lead", "digital commerce", "head of digital"],
        "mobile":    ["head of mobile", "mobile engineering manager", "mobile lead", "ios lead", "android lead"],
        "devops":    ["head of platform", "platform engineering manager", "devops manager", "devops lead",
                      "head of infrastructure", "site reliability"],
        "cms":       ["head of web", "web manager", "digital manager", "web development manager"],
        "ai_ml":     ["head of ai", "ml engineering manager", "head of data", "vp data", "chief data officer"],
        "fullstack":  [],
    }.get(role_type, [])

    if company_size <= 15:
        return role_specific + [
            "cto", "co-founder", "founder", "ceo", "owner", "managing director",
            "head of engineering", "engineering manager", "technical lead",
        ]
    elif company_size <= 100:
        return role_specific + [
            "head of engineering", "engineering manager", "vp engineering", "director of engineering",
            "technical lead", "cto",
            "technical recruiter", "engineering recruiter", "tech recruiter",
            "ceo", "co-founder", "founder",
        ]
    elif company_size <= 500:
        return role_specific + [
            "technical recruiter", "engineering recruiter", "tech recruiter", "software recruiter",
            "talent acquisition", "engineering talent",
            "vp engineering", "director of engineering", "engineering manager",
            "cto",
        ]
    else:
        # Enterprise: only want technical recruiters — emailing CTO is wrong
        return role_specific + [
            "technical recruiter", "engineering recruiter", "tech recruiter", "software recruiter",
            "talent acquisition engineer", "talent acquisition technology",
            "talent acquisition manager", "talent acquisition specialist",
            "hr manager", "hr business partner",
            "engineering manager",
        ]


def _is_excluded_title(title: str) -> bool:
    """Return True if this person's title indicates wrong department."""
    t = (title or "").lower()
    return any(kw in t for kw in _EXCLUDED_TITLE_KEYWORDS)


def _extract_domain_from_url(url: str) -> str | None:
    """Extract root domain from a job URL (e.g. https://jobs.stripe.com/... → stripe.com)."""
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        host = parsed.netloc or parsed.path
        # Strip www. and job board subdomains
        parts = host.lower().split(".")
        # Remove common job-board prefixes that aren't the company domain
        job_board_hosts = {
            "greenhouse", "lever", "workable", "ashbyhq", "bamboohr",
            "jobvite", "smartrecruiters", "taleo", "icims", "jazz",
            "recruitee", "breezy", "pinpointhq", "teamtailor",
        }
        # If it's a job board subdomain like company.lever.co → skip, not useful
        if len(parts) >= 2 and parts[-2] in job_board_hosts:
            return None
        # company.greenhouse.io → greenhouse is the platform, not the company
        if len(parts) >= 3 and parts[-2] in job_board_hosts:
            return None
        # Return last two parts: sub.company.com → company.com
        if len(parts) >= 2:
            return f"{parts[-2]}.{parts[-1]}"
    except Exception:
        pass
    return None


def _search_hunter(company_name: str, company_domain: str = "", job_title: str = "") -> dict | None:
    """
    Hunter.io domain search with smart contact selection:
    1. Fetch up to 100 contacts from the company domain
    2. Filter out wrong-department contacts using Hunter's department field + title keywords
    3. Score remaining contacts by role-type-derived priority list and company size
    4. Return the best match (highest priority score, then highest email confidence)
    """
    keys = _get_hunter_keys()
    if not keys:
        return None

    role_type = _derive_role_type(job_title)
    rate_limited_count = 0

    for key in keys:
        try:
            params = {"api_key": key, "limit": 100}
            if company_domain:
                params["domain"] = company_domain
            else:
                params["company"] = company_name

            r = httpx.get("https://api.hunter.io/v2/domain-search", params=params, timeout=15)

            if r.status_code == 401:
                print(f"[Hunter] Key invalid: {key[:12]}...")
                continue
            if r.status_code == 429:
                rate_limited_count += 1
                if rate_limited_count >= len(keys):
                    print(f"[Hunter] All {len(keys)} keys rate-limited, skipping for now")
                    return None
                print(f"[Hunter] Rate limited, trying next key: {key[:12]}...")
                continue

            data = r.json().get("data", {})
            all_emails = data.get("emails", [])
            if not all_emails:
                continue

            # Parse company size from Hunter response
            company_size = 0
            for field_path in [["company", "size"], ["organization", "headcount"], ["headcount"]]:
                val = data
                for f in field_path:
                    val = val.get(f) if isinstance(val, dict) else None
                if val:
                    try:
                        company_size = int(str(val).split("-")[0].replace("+", "").strip())
                    except Exception:
                        pass
                    break

            print(f"[Hunter] {company_name}: {len(all_emails)} contacts found, size={company_size}, role={role_type}")

            # Step 1: filter by department — keep only tech-relevant departments
            tech_contacts = [
                e for e in all_emails
                if (e.get("department") or "").lower() in _ALLOWED_DEPARTMENTS
                or not e.get("department")  # keep if department unknown — will filter by title next
            ]

            # Step 2: hard-exclude wrong department by title keywords
            tech_contacts = [e for e in tech_contacts if not _is_excluded_title(e.get("position") or "")]

            # If filtering removed everything, fall back to full list (better than no result)
            candidates = tech_contacts if tech_contacts else all_emails

            print(f"[Hunter] {len(candidates)} candidates after department filter")

            # Step 3: score by role-specific title priority + company size
            priority_list = _build_title_priority(role_type, company_size)

            def _score(e) -> tuple:
                pos = (e.get("position") or "").lower()
                # Lower index = better match
                for i, t in enumerate(priority_list):
                    if t in pos:
                        return (i, -(e.get("confidence") or 0))
                return (999, -(e.get("confidence") or 0))

            candidates.sort(key=_score)
            best = candidates[0]

            # Only accept contacts with confidence >= 50 to avoid bounced emails
            if (best.get("confidence") or 0) < 50 and len(candidates) > 1:
                # Try next candidate with acceptable confidence
                acceptable = [e for e in candidates if (e.get("confidence") or 0) >= 50]
                if acceptable:
                    best = acceptable[0]

            first = best.get("first_name") or ""
            last = best.get("last_name") or ""
            name = f"{first} {last}".strip() or None
            print(f"[Hunter] Best contact: {name} — {best.get('position')} "
                  f"(dept={best.get('department')}, confidence={best.get('confidence')})")

            return {
                "name": name,
                "title": best.get("position"),
                "email": best.get("value"),
                "phone": None,
                "linkedin_url": best.get("linkedin"),
                "source": "hunter",
            }
        except Exception as ex:
            print(f"[Hunter] Error with key {key[:12]}...: {ex}")

    return None


def _search_google_linkedin(company_name: str) -> dict | None:
    """
    Fallback: Google search for LinkedIn profile of a hiring person at the company.
    Parses the first linkedin.com/in/ result from Google HTML.
    No API key needed — uses public Google search.
    """
    query = f'site:linkedin.com/in "{company_name}" recruiter OR "hiring manager" OR "talent acquisition"'
    try:
        resp = httpx.get(
            "https://www.google.com/search",
            params={"q": query, "num": 5},
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        # Extract linkedin.com/in/ URLs from Google results
        urls = re.findall(r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+', resp.text)
        if not urls:
            return None

        linkedin_url = urls[0].split("?")[0]  # strip query params

        # Try to extract name from the snippet around the URL
        name = None
        idx = resp.text.find(linkedin_url)
        if idx > 0:
            snippet = resp.text[max(0, idx - 200):idx + 200]
            snippet_clean = re.sub(r"<[^>]+>", " ", snippet)
            # Look for "Name - Title at Company" pattern
            m = re.search(r'([A-Z][a-z]+ [A-Z][a-z]+)\s*[-–|]', snippet_clean)
            if m:
                name = m.group(1)

        return {
            "name": name,
            "title": None,
            "email": None,
            "phone": None,
            "linkedin_url": linkedin_url,
            "source": "google",
        }
    except Exception as e:
        print(f"[Google] Search error: {e}")
    return None


@celery_app.task(name="app.tasks.researcher.research_job_task")
def research_job_task(job_id: str):
    import uuid
    from app.models.job import Job, JobContact, JobStatus

    with SyncSessionLocal() as db:
        job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if not job or not job.company_name:
            return

        # Skip if already has a primary contact with email
        existing = db.query(JobContact).filter(
            JobContact.job_id == job.id,
            JobContact.is_primary == True,
            JobContact.email != None,
        ).first()
        if existing:
            return

        company = job.company_name
        print(f"[Researcher] Researching: {company}")

        # Fetch company size if not already set
        if not job.company_size:
            size = _get_company_size(company)
            if size:
                from app.tasks.company_enrichment import _to_range
                job.company_size = _to_range(size)
                print(f"[Researcher] Company size for {company}: {job.company_size}")

        contact = None

        # Extract domain directly from job URL — more reliable than company name search
        job_domain = (
            _extract_domain_from_url(job.job_url or "")
            or _extract_domain_from_url(job.apply_url or "")
        )
        if job_domain:
            print(f"[Researcher] Extracted domain from job URL: {job_domain}")

        # 1. Hunter.io — primary source (Apollo/Lusha not in use)
        hunter = _search_hunter(company, company_domain=job_domain or "", job_title=job.title or "")
        if hunter and hunter.get("email"):
            print(f"[Researcher] Hunter found: {hunter.get('name')} <{hunter.get('email')}>")
            contact = hunter

        # 2. Apollo fallback (if configured and Hunter found nothing)
        if not contact or not contact.get("email"):
            size_int = _parse_size_range(job.company_size or "")
            apollo = _search_apollo(company, job.title or "", company_size=size_int)
            if apollo and apollo.get("email"):
                print(f"[Researcher] Apollo found: {apollo.get('name')} <{apollo.get('email')}>")
                contact = apollo

        # 3. Lusha fallback
        if not contact or not contact.get("email"):
            lusha = _search_lusha(company, contact.get("name") if contact else "")
            if lusha and (lusha.get("email") or lusha.get("phone")):
                print(f"[Researcher] Lusha found: {lusha.get('name')} <{lusha.get('email')}>")
                if contact:
                    contact["email"] = contact.get("email") or lusha.get("email")
                    contact["phone"] = contact.get("phone") or lusha.get("phone")
                    contact["linkedin_url"] = contact.get("linkedin_url") or lusha.get("linkedin_url")
                else:
                    contact = lusha

        # 4. Google fallback — at least get LinkedIn URL
        if not contact or not contact.get("linkedin_url"):
            google = _search_google_linkedin(company)
            if google:
                print(f"[Researcher] Google found LinkedIn: {google.get('linkedin_url')}")
                if contact:
                    contact["linkedin_url"] = contact.get("linkedin_url") or google.get("linkedin_url")
                    contact["name"] = contact.get("name") or google.get("name")
                else:
                    contact = google

        if contact and (contact.get("email") or contact.get("linkedin_url")):
            # Reset attempt counter on success
            job.research_attempts = 0
            # Remove existing placeholder contacts
            db.query(JobContact).filter(
                JobContact.job_id == job.id,
                JobContact.source != "jd_email",
            ).delete()

            db.add(JobContact(
                job_id=job.id,
                name=contact.get("name"),
                title=contact.get("title"),
                email=contact.get("email"),
                phone=contact.get("phone"),
                linkedin_url=contact.get("linkedin_url"),
                source=contact.get("source"),
                is_primary=True,
            ))
            job.status = JobStatus.ready
            print(f"[Researcher] Contact saved for {company} — status: ready")
        else:
            job.research_attempts = (job.research_attempts or 0) + 1
            if job.research_attempts >= 3:
                job.status = JobStatus.skipped
                print(f"[Researcher] {company} — no contact after {job.research_attempts} attempts, skipping")
            else:
                job.status = JobStatus.researching
                print(f"[Researcher] No contact found for {company} (attempt {job.research_attempts}/3)")

        db.commit()

        if job.status == JobStatus.ready:
            from app.tasks.applicator import apply_job_task
            apply_job_task.delay(str(job.id))


@celery_app.task(name="app.tasks.researcher.research_all_pending_task")
def research_all_pending_task():
    """Re-trigger research for jobs stuck in 'researching' status (max 50 per run to avoid queue floods)."""
    import uuid, redis as _redis
    from app.models.job import Job, JobStatus
    from app.core.config import settings as _cfg

    # Bail out if queue is already deep — don't pile on more research tasks
    try:
        _r = _redis.from_url(_cfg.REDIS_URL)
        queue_depth = _r.llen("celery")
        if queue_depth > 200:
            print(f"[Researcher] Queue depth {queue_depth} too high — skipping research run")
            return
    except Exception:
        pass

    from sqlalchemy import case

    with SyncSessionLocal() as db:
        # Priority 1: manual uploads, Priority 2: newest scraped first. All matched jobs included.
        jobs = (
            db.query(Job)
            .filter(Job.status == JobStatus.researching)
            .order_by(
                case((Job.uploaded_manually == True, 0), else_=1),
                Job.scraped_at.desc().nullslast(),
                Job.created_at.desc(),
            )
            .limit(50)
            .all()
        )
        ids = [str(j.id) for j in jobs]

    print(f"[Researcher] Re-queueing {len(ids)} jobs (manual first, then newest first)")
    for i, jid in enumerate(ids):
        research_job_task.apply_async(args=[jid], countdown=i * 3)
