"""
B2B Lead Generation — two sources:
  1. Apollo.io  — search founders/CTOs/CEOs at startups in target industries + countries
  2. LinkedIn   — Apify company/people scraper for direct outreach prospects

Target profile:
  - Countries  : US, UK, Canada, Australia
  - Industries : SaaS/Tech, E-commerce, Healthcare/MedTech, Real Estate/PropTech
  - Size       : 1–50 employees
  - Roles      : Founder, Co-Founder, CEO, CTO, Head of Engineering, Head of Marketing
"""
from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal


def _get_apollo_keys_from_db() -> list[str]:
    """Read Apollo API keys from GlobalSetting table.
    Keys are stored as comma-separated 'email|key' or plain 'key' entries.
    Falls back to .env values if the DB has nothing configured."""
    from app.models.settings import GlobalSetting
    from app.core.config import settings as cfg

    with SyncSessionLocal() as db:
        row = db.query(GlobalSetting).filter(GlobalSetting.key == "apollo_api_keys").first()
        raw = (row.value or "") if row else ""

    if not raw.strip():
        # fall back to env
        raw = (getattr(cfg, "APOLLO_API_KEYS", None) or getattr(cfg, "APOLLO_API_KEY", None) or "")

    keys = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # Handle 'email|key' format used by the Settings UI
        key = part.split("|")[-1].strip() if "|" in part else part
        if key and "your-apollo" not in key:
            keys.append(key)
    return keys


def _get_next_apollo_key() -> str | None:
    """Round-robin across all configured Apollo keys using a DB cursor.
    Marks the chosen key as 'used this cycle' by advancing the index.
    Returns None if no keys are configured."""
    from app.models.settings import GlobalSetting

    keys = _get_apollo_keys_from_db()
    if not keys:
        return None

    with SyncSessionLocal() as db:
        idx_row = db.query(GlobalSetting).filter(GlobalSetting.key == "apollo_key_index").first()
        current_idx = int(idx_row.value or 0) if idx_row else 0
        # Clamp in case keys were removed
        current_idx = current_idx % len(keys)
        next_idx = (current_idx + 1) % len(keys)

        if idx_row:
            idx_row.value = str(next_idx)
        else:
            db.add(GlobalSetting(key="apollo_key_index", value=str(next_idx)))
        db.commit()

    chosen = keys[current_idx]
    print(f"[Apollo] Using key index {current_idx}/{len(keys)-1}: ...{chosen[-6:]}")
    return chosen

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TARGET_COUNTRIES = ["United States", "United Kingdom", "Canada", "Australia"]
TARGET_COUNTRY_CODES = ["US", "UK", "CA", "AU"]

TARGET_INDUSTRIES = [
    "SaaS / Tech",
    "E-Commerce",
    "Healthcare / MedTech",
    "Real Estate / PropTech",
]

# Apollo industry keyword tags mapped to our industry labels
APOLLO_INDUSTRY_MAP = {
    "SaaS / Tech": ["saas", "software", "technology", "tech startup", "information technology"],
    "E-Commerce": ["ecommerce", "e-commerce", "retail", "shopify", "online store"],
    "Healthcare / MedTech": ["healthcare", "health tech", "medtech", "medical", "health"],
    "Real Estate / PropTech": ["real estate", "proptech", "property", "realty"],
}

# Decision-maker titles to target
TARGET_TITLES = [
    "Founder", "Co-Founder", "CEO", "Chief Executive Officer",
    "CTO", "Chief Technology Officer",
    "Head of Engineering", "VP Engineering",
    "Head of Marketing", "VP Marketing",
    "Managing Director", "Owner",
]

APOLLO_SIZE_RANGES = ["1,10", "11,50"]  # 1–50 employees
MAX_TEAM_SIZE = 50  # Hard cap — skip any lead whose company exceeds this

# Only target early-stage startups
APOLLO_FUNDING_STAGES = ["seed", "pre_seed", "angel", "series_a", "grant", "convertible_note"]

# ---------------------------------------------------------------------------
# 1.  Apollo.io lead import
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.b2b_leads.import_apollo_leads_task")
def import_apollo_leads_task(max_per_industry: int = 25):
    """
    Search Apollo.io for decision-makers at startups matching our ICP.
    Runs daily at 06:00 UTC. Imports up to max_per_industry leads per industry.
    Deduplicates by email + company name.
    """
    import httpx
    from app.core.config import settings as cfg
    from app.models.lead import Lead, LeadActivity, LeadStatus
    from app.tasks.scorer import score_lead_task

    # Load all keys upfront; each industry will rotate to the next key
    api_keys = _get_apollo_keys_from_db()
    if not api_keys:
        print("[Apollo] No API keys configured in Settings → API Keys — skipping")
        return

    with SyncSessionLocal() as db:
        existing_emails = {
            l.contact_email.lower()
            for l in db.query(Lead).filter(Lead.contact_email.isnot(None)).all()
        }
        existing_names = {l.company_name.lower() for l in db.query(Lead).all()}

    total_created = 0

    for industry_label, kw_tags in APOLLO_INDUSTRY_MAP.items():
        # Rotate to next key for each industry request
        key = _get_next_apollo_key() or api_keys[0]

        payload = {
            "person_titles": TARGET_TITLES,
            "organization_num_employees_ranges": APOLLO_SIZE_RANGES,
            "organization_latest_funding_stage": APOLLO_FUNDING_STAGES,
            "person_locations": TARGET_COUNTRIES,
            "q_organization_keyword_tags": kw_tags,
            "contact_email_status": ["verified", "likely to engage"],
            "page": 1,
            "per_page": max_per_industry,
        }

        try:
            resp = httpx.post(
                "https://api.apollo.io/v1/mixed_people/search",
                json=payload,
                headers={"X-Api-Key": key, "Content-Type": "application/json"},
                timeout=30,
            )
        except Exception as e:
            print(f"[Apollo] Request error for {industry_label}: {e}")
            continue

        if resp.status_code == 403:
            err = resp.json().get("error_code", "")
            if err == "API_INACCESSIBLE":
                print(f"[Apollo] ⚠️  Your Apollo API key is on a FREE plan which does not include people search. "
                      f"Upgrade at https://app.apollo.io/ to use B2B scraping.")
            else:
                print(f"[Apollo] 403 Forbidden for {industry_label}: {resp.text[:200]}")
            return  # No point continuing — all industries will fail the same way
        if resp.status_code != 200:
            print(f"[Apollo] {industry_label} → HTTP {resp.status_code}: {resp.text[:200]}")
            continue

        data = resp.json()
        people = data.get("people", []) or data.get("contacts", [])

        created_this_industry = 0
        new_lead_ids = []

        with SyncSessionLocal() as db:
            for person in people:
                email = (person.get("email") or "").strip().lower()
                org = person.get("organization") or person.get("employment_history", [{}])[0] if person.get("employment_history") else {}
                company = (
                    person.get("organization_name")
                    or (org.get("organization_name") if isinstance(org, dict) else "")
                    or ""
                ).strip()

                if not company:
                    continue
                if email and email in existing_emails:
                    continue
                if company.lower() in existing_names:
                    continue
                if not email:
                    # Skip contacts without email — useless for outreach
                    continue

                contact_name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
                contact_title = person.get("title") or ""
                linkedin_url = person.get("linkedin_url") or ""
                website = (
                    person.get("organization", {}).get("website_url")
                    if isinstance(person.get("organization"), dict) else ""
                ) or ""
                company_size_raw = (
                    person.get("organization", {}).get("estimated_num_employees")
                    if isinstance(person.get("organization"), dict) else None
                )
                # Hard cap — skip companies with more than 50 employees
                if company_size_raw and isinstance(company_size_raw, (int, float)) and company_size_raw > MAX_TEAM_SIZE:
                    continue
                company_size = _employees_to_range(company_size_raw)

                # Map country from Apollo location
                location = person.get("city") or person.get("country") or ""
                country = _map_country(location, person.get("country_code", ""))

                lead = Lead(
                    company_name=company,
                    company_website=website or None,
                    industry=industry_label,
                    country=country,
                    company_size=company_size,
                    source="apollo",
                    contact_name=contact_name or None,
                    contact_title=contact_title or None,
                    contact_email=email,
                    contact_linkedin=linkedin_url or None,
                    status=LeadStatus.new,
                    type="startup",
                )
                db.add(lead)
                db.flush()
                db.add(LeadActivity(
                    lead_id=lead.id,
                    action="created",
                    detail=f"Apollo import: {contact_name} ({contact_title}) @ {company}",
                ))
                new_lead_ids.append(str(lead.id))
                existing_emails.add(email)
                existing_names.add(company.lower())
                created_this_industry += 1

            db.commit()

        print(f"[Apollo] {industry_label}: imported {created_this_industry} leads")
        total_created += created_this_industry

        # Queue scoring for new leads
        for i, lid in enumerate(new_lead_ids):
            score_lead_task.apply_async(args=[lid], countdown=i * 3)

    print(f"[Apollo] Total imported: {total_created} leads")
    return total_created


# ---------------------------------------------------------------------------
# 2.  LinkedIn lead import via Apify
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.b2b_leads.import_linkedin_leads_task")
def import_linkedin_leads_task():
    """
    Use Apify (curious_coder~linkedin-jobs-scraper people search) to find
    founders/CTOs at small startups in our target industries + countries.
    Runs Mon + Thu at 07:00 UTC. Deduplicates by email + company name.
    """
    import httpx, time
    import urllib.parse as _up
    from app.models.platform import Platform
    from app.models.lead import Lead, LeadActivity, LeadStatus
    from app.tasks.scorer import score_lead_task

    # Get Apify keys from GlobalSetting (supports multiple accounts)
    from app.models.settings import GlobalSetting
    with SyncSessionLocal() as db:
        setting = db.query(GlobalSetting).filter(GlobalSetting.key == "apify_token").first()
        raw = setting.value if setting else ""
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    api_keys = [p.split("|")[-1].strip() if "|" in p else p for p in parts]
    api_keys = [k for k in api_keys if k and "your-apify" not in k]

    if not api_keys:
        print("[LinkedIn B2B] No Apify keys configured in Settings → API Keys")
        return

    # Search queries — only small startups (≤50 employees), early-stage
    SEARCH_QUERIES = [
        {"keywords": "Founder SaaS startup seed stage 1-50 employees", "location": "United States"},
        {"keywords": "CEO tech startup early stage small team", "location": "United Kingdom"},
        {"keywords": "Founder ecommerce startup small business", "location": "United States"},
        {"keywords": "CTO software startup seed", "location": "Canada"},
        {"keywords": "Founder health tech startup small team", "location": "Australia"},
        {"keywords": "CEO proptech startup seed stage", "location": "United Kingdom"},
        {"keywords": "Founder SaaS startup pre-seed series A", "location": "United States"},
        {"keywords": "Co-Founder startup 1-50 employees", "location": "Australia"},
        {"keywords": "Managing Director digital startup small team", "location": "United Kingdom"},
        {"keywords": "CEO ecommerce startup early stage Canada", "location": "Canada"},
    ]

    actor = "powerai~linkedin-peoples-search-scraper"

    with SyncSessionLocal() as db:
        existing_emails = {
            l.contact_email.lower()
            for l in db.query(Lead).filter(Lead.contact_email.isnot(None)).all()
        }
        existing_names = {l.company_name.lower() for l in db.query(Lead).all()}
        existing_linkedin = {
            l.contact_linkedin.lower()
            for l in db.query(Lead).filter(Lead.contact_linkedin.isnot(None)).all()
        }

    all_prospects = []

    for idx, query in enumerate(SEARCH_QUERIES):
        key = api_keys[idx % len(api_keys)]
        search_url = (
            "https://www.linkedin.com/search/results/people/?"
            + _up.urlencode({
                "keywords": query["keywords"],
                "geoUrn": _linkedin_geo_urn(query["location"]),
                "origin": "GLOBAL_SEARCH_HEADER",
            })
        )
        run_input = {"searchUrl": search_url, "maxResults": 10}

        try:
            r = httpx.post(
                f"https://api.apify.com/v2/acts/{actor}/runs",
                params={"token": key},
                json=run_input,
                timeout=30,
            )
        except Exception as e:
            print(f"[LinkedIn B2B] Failed to start run: {e}")
            continue

        if r.status_code not in (200, 201):
            print(f"[LinkedIn B2B] Actor start failed ({r.status_code}): {r.text[:100]}")
            continue

        run_id = r.json().get("data", {}).get("id")
        if not run_id:
            continue

        # Poll for completion (max 2 minutes)
        status = ""
        sr = None
        for _ in range(24):
            time.sleep(5)
            try:
                sr = httpx.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    params={"token": key},
                    timeout=15,
                )
                status = sr.json().get("data", {}).get("status", "")
                if status == "SUCCEEDED":
                    break
                if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    print(f"[LinkedIn B2B] Run {run_id} failed: {status}")
                    break
            except Exception:
                continue

        if status != "SUCCEEDED" or not sr:
            continue

        dataset_id = sr.json().get("data", {}).get("defaultDatasetId")
        if not dataset_id:
            continue

        try:
            dr = httpx.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                params={"token": key, "format": "json", "clean": "true"},
                timeout=30,
            )
            items = dr.json() if isinstance(dr.json(), list) else []
            all_prospects.extend(items)
        except Exception as e:
            print(f"[LinkedIn B2B] Dataset fetch error: {e}")

    if not all_prospects:
        print("[LinkedIn B2B] No prospects found")
        return

    def _extract_company_from_title(title_str: str) -> str:
        """Extract company name from title like 'CEO at Acme' or 'Founder | Acme Corp'."""
        import re
        for sep in [" at ", " @ ", " | ", " - "]:
            if sep in title_str:
                parts = title_str.split(sep, 1)
                if len(parts) == 2 and parts[1].strip():
                    company = parts[1].split("||")[0].split("|")[0].strip()
                    # Strip trailing descriptions in parens
                    company = re.sub(r'\(.*?\)', '', company).strip()
                    if company and len(company) > 1:
                        return company
        return ""

    new_lead_ids = []
    with SyncSessionLocal() as db:
        created = 0
        for item in all_prospects:
            # Support both old actor fields and new powerai actor fields
            name = (item.get("full_name") or
                    f"{item.get('firstName', '')} {item.get('lastName', '')}".strip())
            title = item.get("title") or item.get("jobTitle") or ""
            company = (item.get("companyName") or item.get("company") or
                       _extract_company_from_title(title)).strip()
            email = (item.get("email") or "").strip().lower()
            linkedin_url = item.get("url") or item.get("profileUrl") or ""

            if not company:
                continue
            if company.lower() in existing_names:
                continue
            if linkedin_url and linkedin_url.lower() in existing_linkedin:
                continue
            if email and email in existing_emails:
                continue

            # Email not required — leads without email get enriched later by enrich_b2b_leads_task

            # Hard cap — skip if LinkedIn reports headcount > 50
            headcount = item.get("companySize") or item.get("employeeCount") or item.get("numEmployees")
            if headcount:
                try:
                    if int(str(headcount).replace("+", "").split("-")[-1].strip()) > MAX_TEAM_SIZE:
                        continue
                except (ValueError, IndexError):
                    pass

            industry = _infer_industry(company, title)
            country = _map_country(item.get("location", ""), item.get("countryCode", ""))

            li_size = str(headcount).strip() if headcount else None
            lead = Lead(
                company_name=company,
                industry=industry,
                country=country,
                company_size=li_size,
                source="linkedin",
                contact_name=name or None,
                contact_title=title or None,
                contact_email=email,
                contact_linkedin=linkedin_url or None,
                status=LeadStatus.new,
                type="startup",
            )
            db.add(lead)
            db.flush()
            db.add(LeadActivity(
                lead_id=lead.id,
                action="created",
                detail=f"LinkedIn scrape: {name} ({title}) @ {company}",
            ))
            new_lead_ids.append(str(lead.id))
            existing_names.add(company.lower())
            if email:
                existing_emails.add(email)
            if linkedin_url:
                existing_linkedin.add(linkedin_url.lower())
            created += 1

        db.commit()
        print(f"[LinkedIn B2B] Imported {created} leads")

    if created > 0:
        try:
            from app.services.alert_service import create_alert
            from app.models.alert import AlertType, AlertSeverity
            create_alert(
                type=AlertType.lead_imported,
                severity=AlertSeverity.info,
                title=f"LinkedIn B2B: {created} new leads imported",
                message=f"{created} leads scraped from LinkedIn and queued for scoring.",
                source="LinkedIn B2B",
            )
        except Exception:
            pass

    for i, lid in enumerate(new_lead_ids):
        score_lead_task.apply_async(args=[lid], countdown=i * 2)

    return len(new_lead_ids)


# ---------------------------------------------------------------------------
# 3.  Email enrichment — find emails for leads that came in without one
# ---------------------------------------------------------------------------

def _get_google_places_keys() -> list[str]:
    """Read Google Places API keys from GlobalSetting (email|key format, comma-separated)."""
    from app.models.settings import GlobalSetting
    with SyncSessionLocal() as db:
        row = db.query(GlobalSetting).filter(GlobalSetting.key == "google_places_api_key").first()
        if not row or not row.value:
            return []
        keys = []
        for part in row.value.split(","):
            part = part.strip()
            if not part:
                continue
            key = part.split("|")[-1].strip()  # supports "email|key" or plain "key"
            if key:
                keys.append(key)
        return keys


def _google_places_lookup(company_name: str) -> dict | None:
    """
    Look up a company on Google Places API. Rotates across all configured keys.
    Returns dict with phone, website, formatted_address — or None if not found.
    """
    import httpx
    keys = _get_google_places_keys()
    if not keys:
        return None
    for key in keys:
        try:
            # Step 1: Text search to get place_id
            search = httpx.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": company_name, "key": key},
                timeout=10,
            )
            data = search.json()
            status = data.get("status")
            if status in ("REQUEST_DENIED", "INVALID_REQUEST", "OVER_QUERY_LIMIT"):
                print(f"[GooglePlaces] Key {key[:12]}... status={status}, trying next")
                from app.services.alert_service import create_alert
                from app.models.alert import AlertType, AlertSeverity
                create_alert(
                    AlertType.key_exhausted,
                    f"Google Places key exhausted — rotating to next",
                    f"Key: {key[:12]}... | Status: {status} | Company: {company_name}",
                    "Google Places",
                    AlertSeverity.warning,
                )
                continue
            results = data.get("results", [])
            if not results:
                print(f"[GooglePlaces] No results for: {company_name}")
                return None

            place_id = results[0]["place_id"]

            # Step 2: Place Details to get phone + website
            details = httpx.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params={
                    "place_id": place_id,
                    "fields": "formatted_phone_number,international_phone_number,website,formatted_address",
                    "key": key,
                },
                timeout=10,
            )
            result = details.json().get("result", {})
            phone = result.get("international_phone_number") or result.get("formatted_phone_number")
            website = result.get("website")
            address = result.get("formatted_address")

            if not phone and not website:
                return None

            print(f"[GooglePlaces] {company_name} → phone={phone} website={website}")
            return {
                "phone": phone,
                "website": website,
                "address": address,
            }
        except Exception as e:
            print(f"[GooglePlaces] Error with key {key[:12]}...: {e}")
            continue
    from app.services.alert_service import create_alert
    from app.models.alert import AlertType, AlertSeverity
    create_alert(
        AlertType.key_error,
        "All Google Places keys exhausted",
        f"No working Google Places key found for: {company_name}",
        "Google Places",
        AlertSeverity.error,
    )
    return None


def _apollo_company_size(company_name: str, website: str | None = None) -> tuple[str | None, int | None]:
    """
    Look up company size via Apollo organization enrichment.
    Returns (range_string, raw_employee_count) — either can be None.
    """
    import httpx
    key = _get_next_apollo_key()
    if not key:
        return None, None
    try:
        payload: dict = {}
        if website:
            payload["domain"] = website.replace("https://", "").replace("http://", "").split("/")[0]
        else:
            payload["name"] = company_name
        r = httpx.post(
            "https://api.apollo.io/v1/organizations/enrich",
            json=payload,
            headers={"X-Api-Key": key, "Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            org = r.json().get("organization") or {}
            num = org.get("estimated_num_employees")
            if num:
                return _employees_to_range(num), int(num)
    except Exception:
        pass
    return None, None


@celery_app.task(name="app.tasks.b2b_leads.enrich_b2b_leads_task")
def enrich_b2b_leads_task(batch_size: int = 10):
    """
    Runs every 30 min.
    Pass 1: picks leads without an email, tries Hunter to find one + Apollo for team size.
    Pass 2: picks leads with email but no company_size, fills size via Apollo.
    """
    from app.models.lead import Lead, LeadActivity, LeadStatus
    from app.tasks.researcher import _search_hunter

    with SyncSessionLocal() as db:
        # Pass 1 — leads missing email
        leads_no_email = (
            db.query(Lead)
            .filter(
                Lead.contact_email.is_(None),
                Lead.company_name.isnot(None),
                Lead.status == LeadStatus.new,
            )
            .order_by(Lead.created_at.asc())
            .limit(batch_size)
            .all()
        )

        enriched = 0
        for lead in leads_no_email:
            try:
                # Step 1: Google Places — get phone + verified domain before Hunter
                if not lead.contact_phone or not lead.company_website:
                    places = _google_places_lookup(lead.company_name)
                    if places:
                        if places.get("phone") and not lead.contact_phone:
                            lead.contact_phone = places["phone"]
                        if places.get("website") and not lead.company_website:
                            lead.company_website = places["website"]
                            # Extract clean domain for Hunter
                            domain = places["website"].replace("https://", "").replace("http://", "").split("/")[0]
                            if not lead.domain:
                                lead.domain = domain
                        db.add(LeadActivity(
                            lead_id=lead.id,
                            action="enriched",
                            detail=f"Google Places: phone={places.get('phone')} website={places.get('website')}",
                        ))

                # Step 2: Hunter — use verified domain if available for better accuracy
                hunter = _search_hunter(lead.company_name, company_domain=lead.domain or "")
                if hunter and hunter.get("email"):
                    lead.contact_email = hunter["email"].lower()
                    if not lead.contact_name and hunter.get("name"):
                        lead.contact_name = hunter["name"]
                    db.add(LeadActivity(
                        lead_id=lead.id,
                        action="enriched",
                        detail=f"Hunter found email: {lead.contact_email}",
                    ))
                    enriched += 1
            except Exception as e:
                print(f"[Enrich] Error for {lead.company_name}: {e}")
                continue

            # Also fill company size if missing, disqualify if > 50
            if not lead.company_size:
                try:
                    size, num = _apollo_company_size(lead.company_name, lead.company_website)
                    if num and num > MAX_TEAM_SIZE:
                        lead.status = LeadStatus.disqualified
                        db.add(LeadActivity(
                            lead_id=lead.id,
                            action="disqualified",
                            detail=f"Apollo: {num} employees — exceeds 50-person cap",
                        ))
                    elif size:
                        lead.company_size = size
                except Exception:
                    pass

        # Pass 2 — leads with email but missing company size
        leads_no_size = (
            db.query(Lead)
            .filter(
                Lead.contact_email.isnot(None),
                Lead.company_name.isnot(None),
                Lead.company_size.is_(None),
                Lead.status == LeadStatus.new,
            )
            .order_by(Lead.created_at.asc())
            .limit(batch_size)
            .all()
        )

        sized = 0
        disqualified = 0
        for lead in leads_no_size:
            try:
                size, num = _apollo_company_size(lead.company_name, lead.company_website)
                if num and num > MAX_TEAM_SIZE:
                    lead.status = LeadStatus.disqualified
                    db.add(LeadActivity(
                        lead_id=lead.id,
                        action="disqualified",
                        detail=f"Apollo: {num} employees — exceeds 50-person cap",
                    ))
                    disqualified += 1
                elif size:
                    lead.company_size = size
                    sized += 1
            except Exception as e:
                print(f"[Enrich Size] Error for {lead.company_name}: {e}")
                continue

        db.commit()
        print(f"[Enrich] Emails: {enriched}/{len(leads_no_email)} | Sizes: {sized}/{len(leads_no_size)} | Disqualified (>50 emp): {disqualified}")


# ---------------------------------------------------------------------------
# 4.  Recovery — ensure scored/approved leads always get an email queued
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.b2b_leads.requeue_b2b_leads_task")
def requeue_b2b_leads_task():
    """
    Runs every 15 min. Handles three recovery cases:
    a) new leads with score ≥ 60 and a contact email → queue outreach
    b) approved leads not yet scheduled → queue outreach
    c) sent leads with no follow-ups scheduled → backfill follow-up sequence
    """
    from app.models.lead import Lead, LeadStatus
    from app.tasks.outreach import send_b2b_email_task

    with SyncSessionLocal() as db:
        # a) Scored new leads ready for outreach
        ready = db.query(Lead).filter(
            Lead.status == LeadStatus.new,
            Lead.score >= 60,
            Lead.contact_email.isnot(None),
        ).all()
        ready_ids = [str(l.id) for l in ready]
        for lead in ready:
            lead.status = LeadStatus.pending_approval  # prevents re-queuing
        if ready:
            db.commit()
        for lid in ready_ids:
            send_b2b_email_task.delay(lid)
        if ready_ids:
            print(f"[B2B Requeue] Queued outreach for {len(ready_ids)} scored leads")

        # b) Approved leads that never got scheduled
        approved = db.query(Lead).filter(
            Lead.status == LeadStatus.approved,
            Lead.contact_email.isnot(None),
        ).all()
        approved_ids = [str(l.id) for l in approved]

    for lid in approved_ids:
        send_b2b_email_task.delay(lid)
    if approved_ids:
        print(f"[B2B Requeue] Re-queued {len(approved_ids)} approved leads")

    # c) Sent leads missing follow-ups
    with SyncSessionLocal() as db:
        sent_leads = db.query(Lead).filter(
            Lead.status.in_([LeadStatus.sent, LeadStatus.opened]),
            Lead.sent_at.isnot(None),
            Lead.follow_up_count == 0,
            Lead.replied_at.is_(None),
        ).all()
        fu_ids = [str(l.id) for l in sent_leads]

    for lid in fu_ids:
        schedule_b2b_followups_task.delay(lid)
    if fu_ids:
        print(f"[B2B Requeue] Queued follow-up scheduling for {len(fu_ids)} sent leads")


# ---------------------------------------------------------------------------
# 4.  B2B follow-up scheduler (separate task — survives worker restarts)
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.b2b_leads.schedule_b2b_followups_task")
def schedule_b2b_followups_task(lead_id: str):
    """
    Schedule follow-up emails for a sent B2B lead.
    Idempotent — safe to run multiple times.
    Follow-up timing: +3 days, +7 days, +14 days after initial send.
    """
    import uuid, secrets
    from app.models.lead import Lead, LeadActivity
    from app.models.email_template import EmailTemplate, TemplateType
    from app.models.email_account import EmailAccount
    from app.services.ai_service import generate_b2b_email
    from app.services.scheduler_service import get_send_datetime
    from datetime import timedelta

    FOLLOWUP_DELAYS = [3, 7, 14]

    with SyncSessionLocal() as db:
        lead = db.query(Lead).filter(Lead.id == uuid.UUID(lead_id)).first()
        if not lead or not lead.sent_at or not lead.contact_email:
            return
        if lead.replied_at:
            return
        if lead.follow_up_count >= len(FOLLOWUP_DELAYS):
            return

        breakdown = lead.score_breakdown or {}
        scheduled_fus = breakdown.get("_followups", {})

        # Resolve sender
        sender_id = breakdown.get("_sender_email_id")
        sender = None
        if sender_id:
            try:
                sender = db.query(EmailAccount).filter(EmailAccount.id == uuid.UUID(sender_id)).first()
            except Exception:
                pass
        if not sender and lead.sender_email_id:
            sender = db.query(EmailAccount).filter(EmailAccount.id == lead.sender_email_id).first()
        if not sender:
            sender = db.query(EmailAccount).filter(
                EmailAccount.is_active == True,
                EmailAccount.is_authorized == True,
                EmailAccount.gmail_token.isnot(None),
                EmailAccount.purpose.in_(["b2b", "both"]),
            ).first()
        if not sender:
            print(f"[B2B FU] No B2B email account found for {lead.company_name} — skipping")
            return

        if "_sender_email_id" not in breakdown:
            breakdown["_sender_email_id"] = str(sender.id)

        created = 0
        for i, delay_days in enumerate(FOLLOWUP_DELAYS, start=1):
            if str(i) in scheduled_fus:
                continue

            template_type = getattr(TemplateType, f"b2b_followup_{i}", None)
            if not template_type:
                continue
            # Industry-specific first, fall back to generic (industry=NULL)
            tmpl = db.query(EmailTemplate).filter(
                EmailTemplate.template_type == template_type,
                EmailTemplate.industry == lead.industry,
                EmailTemplate.is_default == True,
                EmailTemplate.is_active == True,
            ).first()
            if not tmpl:
                tmpl = db.query(EmailTemplate).filter(
                    EmailTemplate.template_type == template_type,
                    EmailTemplate.industry.is_(None),
                    EmailTemplate.is_default == True,
                    EmailTemplate.is_active == True,
                ).first()
            if not tmpl:
                continue

            send_after = lead.sent_at + timedelta(days=delay_days)
            scheduled_at = get_send_datetime(lead.country or "US", sender_email=sender.email, after=send_after)

            content = generate_b2b_email(
                company_name=lead.company_name,
                industry=lead.industry or "",
                country=lead.country or "",
                contact_name=lead.contact_name or "",
                template_subject=tmpl.subject,
                template_body=tmpl.body,
                sender_name="Expandimo Team",
            )

            tracking_id = secrets.token_hex(16)
            scheduled_fus[str(i)] = {
                "scheduled_at": scheduled_at.isoformat(),
                "subject": content.get("subject", ""),
                "body": content.get("body", ""),
                "tracking_id": tracking_id,
                "status": "pending",
            }
            created += 1

        if created:
            from sqlalchemy.orm.attributes import flag_modified
            breakdown["_followups"] = scheduled_fus
            lead.score_breakdown = breakdown
            flag_modified(lead, "score_breakdown")
            db.add(LeadActivity(
                lead_id=lead.id,
                action="followups_scheduled",
                detail=f"Scheduled {created} follow-up(s)",
            ))
            db.commit()
            print(f"[B2B FU] Scheduled {created} follow-ups for {lead.company_name}")


# ---------------------------------------------------------------------------
# 5.  Beat task: send due B2B follow-ups
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.b2b_leads.send_due_b2b_followups_task")
def send_due_b2b_followups_task():
    """Runs every 30 min. Sends due follow-up emails for B2B leads."""
    import uuid
    from app.models.lead import Lead, LeadStatus, LeadActivity
    from app.models.email_account import EmailAccount
    from app.services.gmail_service import send_email
    from app.core.config import settings as app_settings
    from datetime import datetime

    now = datetime.utcnow()

    with SyncSessionLocal() as db:
        candidates = db.query(Lead).filter(
            Lead.status.in_([LeadStatus.sent, LeadStatus.opened, LeadStatus.follow_up_1, LeadStatus.follow_up_2]),
            Lead.replied_at.is_(None),
            Lead.sent_at.isnot(None),
        ).all()

        for lead in candidates:
            breakdown = lead.score_breakdown or {}
            followups = breakdown.get("_followups", {})
            if not followups:
                continue

            sender_id = breakdown.get("_sender_email_id")
            if not sender_id:
                continue
            sender = db.query(EmailAccount).filter(EmailAccount.id == uuid.UUID(sender_id)).first()
            if not sender or not sender.gmail_token:
                continue

            for fu_num_str, fu_data in sorted(followups.items(), key=lambda x: int(x[0])):
                if fu_data.get("status") != "pending":
                    continue

                scheduled_str = fu_data.get("scheduled_at", "")
                if not scheduled_str:
                    continue

                try:
                    scheduled_dt = datetime.fromisoformat(scheduled_str)
                except Exception:
                    continue

                if scheduled_dt > now:
                    break  # future follow-ups not due yet

                try:
                    send_email(
                        token_json=sender.gmail_token,
                        sender=sender.email,
                        to=lead.contact_email,
                        subject=fu_data.get("subject", "Following up"),
                        body=fu_data.get("body", ""),
                        tracking_pixel_url=f"{app_settings.TRACKING_PIXEL_URL}/pixel/{fu_data.get('tracking_id')}",
                        thread_id=lead.gmail_thread_id,
                    )
                    fu_data["status"] = "sent"
                    fu_data["sent_at"] = now.isoformat()
                    fu_num = int(fu_num_str)
                    lead.follow_up_count = fu_num
                    lead.status = getattr(LeadStatus, f"follow_up_{fu_num}", LeadStatus.follow_up_1)
                    breakdown["_followups"] = followups
                    lead.score_breakdown = breakdown
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(lead, "score_breakdown")
                    db.add(LeadActivity(
                        lead_id=lead.id,
                        action=f"follow_up_{fu_num}_sent",
                        detail=f"Follow-up #{fu_num} sent to {lead.contact_email}",
                    ))
                    db.commit()
                    print(f"[B2B FU] Sent follow-up #{fu_num} to {lead.company_name}")
                except Exception as e:
                    print(f"[B2B FU] Error sending follow-up to {lead.company_name}: {e}")
                break  # only one follow-up per lead per tick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _employees_to_range(num) -> str | None:
    if num is None:
        return None
    try:
        n = int(num)
    except (TypeError, ValueError):
        return str(num)
    if n <= 10:
        return "1-10"
    elif n <= 50:
        return "11-50"
    elif n <= 200:
        return "51-200"
    elif n <= 500:
        return "201-500"
    else:
        return "500+"


def _map_country(location: str, country_code: str = "") -> str:
    """Map a free-text location or country code to a clean country name."""
    loc = (location or "").lower()
    code = (country_code or "").upper()
    if code == "US" or "united states" in loc or "usa" in loc:
        return "US"
    if code == "GB" or "united kingdom" in loc or "uk" in loc or "england" in loc or "london" in loc:
        return "UK"
    if code == "CA" or "canada" in loc:
        return "CA"
    if code == "AU" or "australia" in loc:
        return "AU"
    return code or "US"


def _infer_industry(company: str, title: str) -> str:
    combined = (company + " " + title).lower()
    if any(k in combined for k in ["shopify", "woocommerce", "ecommerce", "e-commerce", "retail"]):
        return "E-Commerce"
    if any(k in combined for k in ["health", "medical", "medtech", "clinic", "pharma"]):
        return "Healthcare / MedTech"
    if any(k in combined for k in ["real estate", "property", "realty", "proptech"]):
        return "Real Estate / PropTech"
    return "SaaS / Tech"


def _linkedin_geo_urn(location: str) -> str:
    """Return LinkedIn geoUrn for common countries."""
    urns = {
        "United States": "103644278",
        "United Kingdom": "101165590",
        "Canada": "101174742",
        "Australia": "101452733",
    }
    return urns.get(location, "103644278")
