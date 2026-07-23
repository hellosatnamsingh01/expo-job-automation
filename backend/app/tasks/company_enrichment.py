"""
Company size enrichment — fires after each job is scraped.
Sources (in order):
  1. Wikidata SPARQL — structured employee count for known companies
  2. Wikipedia REST summary — parse extract text for employee mentions
Maps found numbers to LinkedIn-style ranges and stores in jobs.company_size.
Never raises — failures are silent so the scraper pipeline is never blocked.
"""

from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
import re
import requests as _requests

HEADERS = {"User-Agent": "Expandimo-Bot/1.0 (company size enrichment; contact@expandimo.com)"}

# ── LinkedIn-style range buckets ─────────────────────────────────────────────

RANGES = [
    (1,       10,      "1-10"),
    (11,      50,      "11-50"),
    (51,      200,     "51-200"),
    (201,     500,     "201-500"),
    (501,     1_000,   "501-1,000"),
    (1_001,   5_000,   "1,001-5,000"),
    (5_001,   10_000,  "5,001-10,000"),
    (10_001,  10**9,   "10,000+"),
]


def _to_range(n: int) -> str:
    for lo, hi, label in RANGES:
        if lo <= n <= hi:
            return label
    return "10,000+"


def _extract_number(text: str) -> int | None:
    """Pull the most prominent employee-count number from a block of text."""
    text = text.lower()

    # Each tuple: (pattern, multiply_by_1000)
    patterns = [
        (r"([\d,]+)\s*\+\s*employees", False),           # "10,000+ employees"
        (r"([\d,]+)\s+employees", False),                 # "5,000 employees"
        (r"employees[:\s]+([0-9,]+)", False),             # "employees: 5,000"
        (r"(?:team|staff|workforce)\s+of\s+([\d,]+)", False),  # "team of 200"
        (r"(?:about|around|approximately|over|nearly)\s+([\d,]+)\s+(?:people|staff|employees|workers)", False),
        (r"([\d.]+)\s*k\s+employees", True),              # "5k employees" → multiply by 1000
        (r"company\s+size[:\s]+([0-9,]+)", False),        # "Company size: 200"
        (r"([\d,]+)[- ]person\s+(?:team|company|startup|organization|firm)", False),  # "50-person startup"
        (r"([\d,]+)\s+(?:staff\s+members?|team\s+members?|people\s+strong)", False),  # "1,200 staff members"
    ]

    for pat, use_k in patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).replace(",", "").strip()
            if not raw:
                continue
            try:
                n = int(float(raw) * 1000) if use_k else int(raw)
            except (ValueError, OverflowError):
                continue
            if n > 0:
                return n

    # Range like "1,000-5,000 employees"
    m = re.search(r"([\d,]+)\s*[-–]\s*([\d,]+)\s+employees", text)
    if m:
        lo = int(m.group(1).replace(",", ""))
        hi = int(m.group(2).replace(",", ""))
        return (lo + hi) // 2

    return None


def _range_from_text(text: str) -> str | None:
    # Already-formatted LinkedIn ranges in text (e.g. "51-200 employees")
    for _, _, label in RANGES:
        if label in text:
            return label
    # Extract a number and bucket it
    n = _extract_number(text)
    if n and n > 0:
        return _to_range(n)
    return None


# ── Source 1: Wikidata SPARQL ────────────────────────────────────────────────

def _wikidata(company_name: str) -> str | None:
    """
    Query Wikidata for employee count (P1124) by company label.
    Returns a LinkedIn-style range or None.
    """
    sparql = f"""
    SELECT ?employees WHERE {{
      ?company wdt:P31 wd:Q4830453 ;
               rdfs:label "{company_name}"@en ;
               wdt:P1124 ?employees .
    }} LIMIT 1
    """
    try:
        r = _requests.get(
            "https://query.wikidata.org/sparql",
            params={"query": sparql, "format": "json"},
            headers=HEADERS,
            timeout=10,
        )
        bindings = r.json().get("results", {}).get("bindings", [])
        if bindings:
            val = bindings[0].get("employees", {}).get("value", "")
            n = int(float(val))
            if n > 0:
                return _to_range(n)
    except Exception:
        pass

    # Broader search — fuzzy match via Wikidata entity search
    try:
        search_r = _requests.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": company_name,
                "language": "en",
                "type": "item",
                "limit": 3,
                "format": "json",
            },
            headers=HEADERS,
            timeout=8,
        )
        items = search_r.json().get("search", [])
        for item in items:
            qid = item.get("id")
            if not qid:
                continue
            # Fetch P1124 (number of employees) for this entity
            claims_r = _requests.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbgetclaims",
                    "entity": qid,
                    "property": "P1124",
                    "format": "json",
                },
                headers=HEADERS,
                timeout=8,
            )
            claims = claims_r.json().get("claims", {}).get("P1124", [])
            if claims:
                # Take the most recent value (last in list)
                for claim in reversed(claims):
                    try:
                        val = claim["mainsnak"]["datavalue"]["value"]["amount"]
                        n = int(float(val.lstrip("+")))
                        if n > 0:
                            return _to_range(n)
                    except Exception:
                        continue
    except Exception:
        pass

    return None


# ── Source 2: Wikipedia REST summary ────────────────────────────────────────

def _wikipedia(company_name: str) -> str | None:
    """
    Search Wikipedia for the company and parse the summary extract
    for any employee count mention.
    """
    try:
        # Search for the article
        search_r = _requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": company_name,
                "srlimit": 3,
                "format": "json",
            },
            headers=HEADERS,
            timeout=8,
        )
        results = search_r.json().get("query", {}).get("search", [])
        if not results:
            return None

        for hit in results:
            title = hit["title"]
            # Only proceed if title plausibly matches
            name_words = [w.lower() for w in company_name.split() if len(w) > 2]
            if not any(w in title.lower() for w in name_words):
                continue

            # Fetch plain text summary via REST API
            rest_r = _requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}",
                headers=HEADERS,
                timeout=8,
            )
            data = rest_r.json()
            extract = data.get("extract", "")
            result = _range_from_text(extract)
            if result:
                return result

            # Fallback: fetch full wikitext section 0 for infobox employee count
            wikitext_r = _requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "revisions",
                    "titles": title,
                    "rvprop": "content",
                    "rvsection": "0",
                    "format": "json",
                },
                headers=HEADERS,
                timeout=8,
            )
            pages = wikitext_r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                content = page.get("revisions", [{}])[0].get("*", "")
                # Infobox: | num_employees = 90,000
                m = re.search(r"\|\s*num_employees\s*=\s*([^\n\|<\[]+)", content, re.IGNORECASE)
                if m:
                    result = _range_from_text(m.group(1))
                    if result:
                        return result
                result = _range_from_text(content[:4000])
                if result:
                    return result

    except Exception:
        pass

    return None


# ── Source 3: Hunter.io ──────────────────────────────────────────────────────

def _hunter(company_name: str) -> str | None:
    """
    Use Hunter.io domain-search to find company size.
    Hunter returns a 'headcount' field for some companies.
    """
    try:
        from app.tasks.researcher import _get_hunter_keys
        keys = _get_hunter_keys()
        if not keys:
            return None
        for key in keys:
            r = _requests.get(
                "https://api.hunter.io/v2/domain-search",
                params={"company": company_name, "api_key": key, "limit": 1},
                timeout=10,
            )
            if r.status_code == 429:
                continue  # quota exhausted, try next key
            if r.status_code != 200:
                continue
            data = r.json().get("data", {}) or {}
            # Hunter returns headcount as int for some companies
            headcount = data.get("headcount") or data.get("company_size") or data.get("size")
            if headcount:
                try:
                    n = int(str(headcount).replace(",", "").replace("+", "").split("-")[0].strip())
                    if n > 0:
                        return _to_range(n)
                except (ValueError, IndexError):
                    pass
            # Also check if the value is already a range string
            if isinstance(headcount, str) and "-" in headcount:
                result = _range_from_text(headcount + " employees")
                if result:
                    return result
    except Exception:
        pass
    return None


# ── Source 4: Claude AI ───────────────────────────────────────────────────────

_VALID_RANGES = {"1-10", "11-50", "51-200", "201-500", "501-1,000", "1,001-5,000", "5,001-10,000", "10,000+"}

def _claude_ai(company_name: str, description: str) -> str | None:
    """
    Ask Claude to estimate company size from company name + description.
    Uses the cheapest model (Haiku) with a tiny prompt.
    """
    if not description or len(description) < 50:
        return None
    try:
        from app.services.ai_service import _ai_chat
        prompt = (
            f"Company: {company_name}\n"
            f"Job description excerpt: {description[:800]}\n\n"
            "Based on the above, estimate the company's employee count using LinkedIn ranges. "
            "Reply with ONLY one of these exact values: 1-10, 11-50, 51-200, 201-500, 501-1,000, 1,001-5,000, 5,001-10,000, 10,000+, unknown"
        )
        reply = (_ai_chat(prompt, max_tokens=15) or "").strip().strip('"').strip("'")
        if reply in _VALID_RANGES:
            return reply
    except Exception:
        pass
    return None


# ── Main task ─────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.company_enrichment.enrich_company_size_task",
    max_retries=2,
    default_retry_delay=600,
)
def enrich_company_size_task(job_id: str):
    """
    Enrich company_size for a single job.
    Order: description regex → Claude AI → Hunter → Wikidata → Wikipedia.
    Silently exits if company_size is already set.
    """
    import uuid as _uuid
    from app.models.job import Job

    with SyncSessionLocal() as db:
        job = db.query(Job).filter(Job.id == _uuid.UUID(job_id)).first()
        if not job or job.company_size:
            return
        company = (job.company_name or "").strip()
        description = (job.job_description or "").strip()
        if not company:
            return

    # 1. Regex extraction from job description (free, instant)
    result = _range_from_text(description) if description else None

    # 2. Claude AI — infers size from company name + description context
    if not result:
        result = _claude_ai(company, description)

    # 3. Hunter.io domain search
    if not result:
        result = _hunter(company)

    # 4. Wikidata SPARQL → Wikipedia REST
    if not result:
        print(f"[CompanyEnrich] Trying Wikidata/Wikipedia: {company}")
        result = _wikidata(company) or _wikipedia(company)

    if result:
        with SyncSessionLocal() as db:
            job = db.query(Job).filter(Job.id == _uuid.UUID(job_id)).first()
            if job and not job.company_size:
                job.company_size = result
                db.commit()
                print(f"[CompanyEnrich] ✓ {company} → {result}")
    else:
        print(f"[CompanyEnrich] ✗ Not found: {company}")


@celery_app.task(name="app.tasks.company_enrichment.backfill_company_sizes_task")
def backfill_company_sizes_task():
    """
    Enqueue enrichment for all jobs missing company_size.
    Staggered 3 seconds apart to avoid API rate limits.
    """
    from app.models.job import Job

    with SyncSessionLocal() as db:
        jobs = db.query(Job.id, Job.company_name).filter(
            Job.company_size.is_(None),
            Job.company_name.isnot(None),
        ).all()

    print(f"[CompanyEnrich] Backfill: {len(jobs)} jobs to enrich")
    for i, (job_id, _) in enumerate(jobs):
        enrich_company_size_task.apply_async(args=[str(job_id)], countdown=i * 3)
