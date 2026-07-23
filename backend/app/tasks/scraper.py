from app.tasks.celery_app import celery_app
from app.db.base import SyncSessionLocal
from datetime import datetime
import hashlib
import httpx
import xml.etree.ElementTree as ET
import re


def _parse_pub_date(date_str: str):
    """Parse common date formats from RSS pubDate and API fields into datetime."""
    if not date_str:
        return None
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


@celery_app.task(name="app.tasks.scraper.scrape_all_platforms_task")
def scrape_all_platforms_task():
    """Queue platforms that are due based on their own scrape_frequency_hours."""
    from app.models.platform import Platform
    from datetime import timedelta
    now = datetime.utcnow()
    with SyncSessionLocal() as db:
        platforms = db.query(Platform).filter(Platform.is_active == True).all()
        ids = []
        for p in platforms:
            freq_hours = p.scrape_frequency_hours or 24
            if p.last_scraped_at is None:
                ids.append(str(p.id))  # never scraped — run immediately
            elif now - p.last_scraped_at >= timedelta(hours=freq_hours):
                ids.append(str(p.id))  # due for re-scrape
    for pid in ids:
        scrape_platform_task.delay(pid)
    if ids:
        print(f"[Scraper] Queued {len(ids)} platform(s) due for scraping")


@celery_app.task(name="app.tasks.scraper.scrape_platform_task")
def scrape_platform_task(platform_id: str):
    from app.models.platform import Platform
    from app.models.job import Job, JobContact
    import uuid

    with SyncSessionLocal() as db:
        platform = db.query(Platform).filter(Platform.id == uuid.UUID(platform_id)).first()
        if not platform:
            return

        scrape_type = platform.scrape_type.value if hasattr(platform.scrape_type, 'value') else str(platform.scrape_type)

        # URL-based override — lets us use dedicated scrapers without a DB migration
        url = platform.url or ""
        if "bark.com" in url:
            scraper_fn = scrape_bark
        elif "linkedin.com" in url:
            scraper_fn = scrape_linkedin_apify
        elif "jobs.wordpress.net" in url:
            scraper_fn = scrape_wordpress_jobs
        elif "wpremotework.com" in url:
            scraper_fn = scrape_wpremotework
        elif "jobicy.com" in url:
            scraper_fn = scrape_jobicy
        elif "remoteok.com" in url:
            scraper_fn = scrape_remoteok
        elif "remotive.com" in url:
            scraper_fn = scrape_remotive
        else:
            scraper_fn = SCRAPERS.get(scrape_type, scrape_custom)

        try:
            jobs_data = scraper_fn(platform.url, platform.keywords, platform.scrape_config)
        except Exception as e:
            print(f"[Scraper] {platform.name} error: {e}")
            jobs_data = []
            from app.services.alert_service import create_alert
            from app.models.alert import AlertType, AlertSeverity
            create_alert(
                type=AlertType.platform_error,
                severity=AlertSeverity.error,
                title=f"{platform.name} scrape failed",
                message=str(e)[:500],
                source=platform.name,
            )

        created = 0
        new_job_ids = []
        for job in jobs_data:
            title = (job.get("title") or "").strip()
            company = (job.get("company_name") or "").strip()
            if not title:
                continue

            dedup = hashlib.sha256(f"{title.lower()}|{company.lower()}".encode()).hexdigest()[:64]
            if db.query(Job).filter(Job.dedup_hash == dedup).first():
                continue

            raw_desc = job.get("job_description") or ""
            # Store raw description now — enrich_job_descriptions_task summarises later
            job_desc = raw_desc[:2000] if raw_desc else None

            new_job = Job(
                title=title,
                company_name=company or None,
                company_size=job.get("company_size") or None,
                location=job.get("location"),
                country=job.get("country"),
                job_url=job.get("job_url"),
                apply_url=job.get("apply_url"),
                job_description=job_desc,
                platform_id=uuid.UUID(platform_id),
                dedup_hash=dedup,
                posted_at=job.get("posted_at"),
                scraped_at=datetime.utcnow(),
            )
            db.add(new_job)
            db.flush()

            if job.get("contact_email"):
                db.add(JobContact(job_id=new_job.id, email=job["contact_email"], source="jd_email", is_primary=True))

            new_job_ids.append(str(new_job.id))
            created += 1

        platform.last_scraped_at = datetime.utcnow()
        db.commit()
        print(f"[Scraper] {platform.name}: {created} new jobs added")
        if created > 0:
            from app.services.alert_service import create_alert
            from app.models.alert import AlertType, AlertSeverity
            create_alert(
                type=AlertType.platform_ok,
                severity=AlertSeverity.info,
                title=f"{platform.name}: {created} new jobs scraped",
                message=f"Scrape completed successfully. {created} new jobs added.",
                source=platform.name,
            )

    # Queue match tasks only for the newly scraped jobs — avoids re-matching the
    # entire DB on every scrape run. The hourly beat handles full re-matching.
    if new_job_ids:
        from app.tasks.matcher import match_job_task
        from app.tasks.company_enrichment import enrich_company_size_task
        for i, job_id in enumerate(new_job_ids):
            match_job_task.apply_async(args=[job_id], countdown=i * 2)
            enrich_company_size_task.apply_async(args=[job_id], countdown=i * 2 + 1)


# ── Scrapers (all synchronous, using httpx) ──────────────────────────────────

def scrape_wordpress_jobs(url, keywords, config) -> list:
    """
    Scraper for jobs.wordpress.net
    Listing page: .job-card elements
    Detail page: .job-detail__body (description), .job-sidebar__detail-value (meta), Apply Now link
    """
    import time

    base_url = "https://jobs.wordpress.net"
    kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]
    jobs = []

    try:
        r = httpx.get(base_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")

        cards = soup.select("a.job-card")
        print(f"[WPJobs] Found {len(cards)} job cards")

        for card in cards:
            title = (card.select_one(".job-card__title") or {}).get_text(strip=True) if card.select_one(".job-card__title") else ""
            company = (card.select_one(".job-card__company") or {}).get_text(strip=True) if card.select_one(".job-card__company") else ""
            category = (card.select_one(".job-card__badge") or {}).get_text(strip=True) if card.select_one(".job-card__badge") else ""
            job_url = card.get("href", "")

            # Location and job type from meta spans
            meta_spans = card.select(".job-card__meta span")
            location_raw = meta_spans[0].get_text(strip=True) if len(meta_spans) > 0 else ""
            job_type = meta_spans[1].get_text(strip=True) if len(meta_spans) > 1 else ""

            # Clean location — strip emoji
            location = re.sub(r"[^\x00-\x7F]+", "", location_raw).strip()
            is_remote = "remote" in location_raw.lower() or "🌎" in location_raw

            if not title:
                continue

            # Filter by keywords if configured
            if kw_list:
                text = f"{title} {company} {category}".lower()
                if not any(kw in text for kw in kw_list):
                    continue

            # Fetch detail page for description + apply link
            description = ""
            apply_url = ""
            company_website = ""
            sidebar_location = ""
            budget = ""

            if job_url:
                try:
                    time.sleep(0.5)  # polite delay
                    dr = httpx.get(job_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12, follow_redirects=True)
                    dsoup = BeautifulSoup(dr.text, "html.parser")

                    # Description
                    body_el = dsoup.select_one(".job-detail__body")
                    if body_el:
                        description = body_el.get_text(separator="\n", strip=True)[:3000]

                    # Sidebar meta: Company, Job Type, Location, Budget
                    for detail in dsoup.select(".job-sidebar__detail"):
                        label_el = detail.select_one(".job-sidebar__detail-label")
                        value_el = detail.select_one(".job-sidebar__detail-value")
                        if label_el and value_el:
                            label = label_el.get_text(strip=True).lower()
                            value = value_el.get_text(strip=True)
                            if "location" in label:
                                sidebar_location = value
                            elif "budget" in label:
                                budget = value
                            elif "company" in label and not company:
                                company = value

                    # Apply Now link → company's own website
                    apply_el = dsoup.select_one(".job-sidebar__apply a")
                    if apply_el:
                        apply_url = apply_el.get("href", "")

                except Exception as e:
                    print(f"[WPJobs] Detail page error for {job_url}: {e}")

            # Determine country from location
            location_text = (sidebar_location or location_raw).lower()
            country = None
            if "remote" in location_text or "🌎" in location_text:
                country = None  # global remote — scheduler will use default
            elif "uk" in location_text or "united kingdom" in location_text:
                country = "United Kingdom"
            elif "us" in location_text or "united states" in location_text or "usa" in location_text:
                country = "United States"
            elif "canada" in location_text:
                country = "Canada"
            elif "australia" in location_text:
                country = "Australia"

            # Extract direct email if apply link is a mailto:
            contact_email = None
            if apply_url.startswith("mailto:"):
                contact_email = apply_url.replace("mailto:", "").split("?")[0].strip()

            jobs.append({
                "title": title,
                "company_name": company,
                "location": sidebar_location or location_raw,
                "country": country,
                "job_url": job_url,
                "job_description": description,
                "job_type": job_type,
                "category": category,
                "apply_url": apply_url,
                "budget": budget,
                "contact_email": contact_email,
            })

    except Exception as e:
        print(f"[WPJobs] Error: {e}")

    print(f"[WPJobs] Returning {len(jobs)} jobs")
    return jobs

def scrape_weworkremotely(url, keywords, config) -> list:
    """
    WeWorkRemotely via public RSS feed.
    Title format: 'CompanyName: Job Title | Extra Info'
    Fields: title, company (from title), region, skills, category, link.
    """
    kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]

    def _kw_match(kw: str, text: str) -> bool:
        if " " in kw:
            return kw in text
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))

    # Primary URL from platform config, with extra feeds from scrape_config
    feed_urls = [url] if url else ["https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss"]
    if config and isinstance(config, dict):
        for extra in config.get("extra_feeds", []):
            if extra not in feed_urls:
                feed_urls.append(extra)

    seen_links = set()
    raw_items = []
    for feed_url in feed_urls:
        try:
            r = httpx.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
            root = ET.fromstring(r.text)
            for item in root.iter("item"):
                link = (item.findtext("link") or item.findtext("guid") or "").strip()
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                raw_items.append(item)
        except Exception as e:
            print(f"[WWR] Feed error ({feed_url}): {e}")

    print(f"[WWR] {len(raw_items)} unique items across all feeds")

    jobs = []
    for item in raw_items:
        raw_title = (item.findtext("title") or "").strip()
        region = (item.findtext("region") or "Anywhere in the World").strip()
        skills = (item.findtext("skills") or "").strip()
        category = (item.findtext("category") or "").strip()
        link = (item.findtext("link") or item.findtext("guid") or "").strip()
        desc_html = (item.findtext("description") or "").strip()
        description = re.sub(r"<[^>]+>", "", desc_html).strip()[:3000]

        # Extract company and title: "CompanyName: Job Title | Extra"
        if ": " in raw_title:
            company, job_title = raw_title.split(": ", 1)
            job_title = job_title.split(" | ")[0].strip()
        else:
            company = ""
            job_title = raw_title.split(" | ")[0].strip()

        if not job_title:
            continue

        # Filter by keywords against title + company + skills + description
        if kw_list:
            search_text = f"{job_title} {company} {skills} {description[:300]}".lower()
            if not any(_kw_match(kw, search_text) for kw in kw_list):
                continue

        pub_date_str = (item.findtext("pubDate") or "").strip()
        posted_at = _parse_pub_date(pub_date_str)

        jobs.append({
            "title": job_title,
            "company_name": company,
            "location": region,
            "job_url": link,
            "apply_url": link,
            "job_description": description or None,
            "posted_at": posted_at,
        })

    print(f"[WWR] Returning {len(jobs)} matched jobs")
    return jobs


def scrape_remoteok(url, keywords, config) -> list:
    """
    RemoteOK public JSON API — https://remoteok.com/api
    Returns up to 100 latest remote jobs with tags, description, apply URL.
    Filtered locally by keywords against position + tags + description.
    """
    kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]

    def _kw_match(kw: str, text: str) -> bool:
        if " " in kw:
            return kw in text
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))

    jobs = []
    try:
        r = httpx.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
            follow_redirects=True,
        )
        data = r.json()
        print(f"[RemoteOK] {len([d for d in data if isinstance(d, dict) and 'position' in d])} jobs in API")

        for item in data:
            if not isinstance(item, dict) or "position" not in item:
                continue

            title = (item.get("position") or "").strip()
            company = (item.get("company") or "").strip()
            tags = item.get("tags") or []
            desc_html = item.get("description") or ""
            description = re.sub(r"<[^>]+>", "", desc_html).strip()[:3000]
            apply_url = item.get("apply_url") or item.get("url") or ""
            job_url = item.get("url") or ""

            if not title:
                continue

            if kw_list:
                search_text = f"{title} {company} {' '.join(tags)} {description[:300]}".lower()
                if not any(_kw_match(kw, search_text) for kw in kw_list):
                    continue

            epoch = item.get("epoch")
            posted_at = datetime.utcfromtimestamp(int(epoch)) if epoch else None

            jobs.append({
                "title": title,
                "company_name": company,
                "location": "Remote",
                "job_url": job_url,
                "apply_url": apply_url,
                "job_description": description or None,
                "posted_at": posted_at,
            })

    except Exception as e:
        print(f"[RemoteOK] API error: {e}")

    print(f"[RemoteOK] Returning {len(jobs)} matched jobs")
    return jobs


def scrape_jobicy(url, keywords, config) -> list:
    """
    Jobicy via multiple RSS feeds to maximise coverage.
    Fetches: general feed + engineering category + keyword searches.
    Detail pages are Cloudflare-protected — apply_url not available directly.
    """
    JL_NS = "https://jobicy.com"
    CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
    kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]

    def _kw_match(kw: str, text: str) -> bool:
        if " " in kw:
            return kw in text
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))

    def _parse_country(location: str) -> str:
        loc = location.lower()
        if "usa" in loc or "united states" in loc:
            return "United States"
        if "uk" in loc or "united kingdom" in loc:
            return "United Kingdom"
        if "canada" in loc:
            return "Canada"
        if "australia" in loc:
            return "Australia"
        return None

    # Base feeds — always fetched for broad coverage
    feed_urls = [
        "https://jobicy.com/?feed=job_feed",
        "https://jobicy.com/?feed=job_feed&job_categories=dev",
        "https://jobicy.com/?feed=job_feed&job_categories=engineering",
        "https://jobicy.com/?feed=job_feed&search_keywords=developer",
        "https://jobicy.com/?feed=job_feed&search_keywords=wordpress",
        "https://jobicy.com/?feed=job_feed&search_keywords=php",
        "https://jobicy.com/?feed=job_feed&search_keywords=shopify",
    ]

    # Extra URLs from platform scrape_config: {"extra_feeds": ["url1", "url2"]}
    if config and isinstance(config, dict):
        for extra in config.get("extra_feeds", []):
            if extra not in feed_urls:
                feed_urls.append(extra)

    seen_links = set()
    raw_items = []  # (title, link, company, location, job_type, pub_date, desc_html)

    for feed_url in feed_urls:
        try:
            r = httpx.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
            root = ET.fromstring(r.text)
            for item in root.iter("item"):
                link = (item.findtext("link") or "").strip()
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                raw_items.append(item)
        except Exception as e:
            print(f"[Jobicy] Feed error ({feed_url}): {e}")

    print(f"[Jobicy] {len(raw_items)} unique items across all feeds")

    jobs = []
    for item in raw_items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        company = (item.findtext(f"{{{JL_NS}}}company") or "").strip()
        location = (item.findtext(f"{{{JL_NS}}}location") or "").strip()
        job_type = (item.findtext(f"{{{JL_NS}}}job_type") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        desc_html = item.findtext(f"{{{CONTENT_NS}}}encoded") or item.findtext("description") or ""
        description = re.sub(r"<[^>]+>", "", desc_html).strip()[:3000]

        if not title:
            continue

        if kw_list:
            search_text = f"{title} {company} {description[:500]}".lower()
            if not any(_kw_match(kw, search_text) for kw in kw_list):
                continue

        jobs.append({
            "title": title,
            "company_name": company,
            "location": location,
            "country": _parse_country(location),
            "job_url": link,
            "apply_url": link,
            "job_description": description,
            "job_type": job_type,
            "posted_at": _parse_pub_date(pub_date),
        })

    print(f"[Jobicy] Returning {len(jobs)} matched jobs")
    return jobs


def scrape_indeed(url, keywords, config) -> list:
    """
    Indeed via HasData API — https://api.hasdata.com/scrape/indeed/job
    Searches multiple keyword queries, parses returned HTML with BeautifulSoup.
    Requires HASDATA_API_KEY in environment or scrape_config.
    """
    import os
    from bs4 import BeautifulSoup

    # Support multiple API keys — rotates to next when one is exhausted
    cfg = config or {}
    raw_keys = cfg.get("api_keys") or []
    # Support both old string format and new {key, email} object format
    api_keys = [k["key"] if isinstance(k, dict) else k for k in raw_keys if (k["key"] if isinstance(k, dict) else k)]
    if not api_keys:
        single = cfg.get("api_key") or os.environ.get("HASDATA_API_KEY", "")
        if single:
            api_keys = [single]
    if not api_keys:
        print("[Indeed] No HasData API key configured")
        return []

    current_key_index = [0]  # mutable so inner function can update it

    def _get_key():
        return api_keys[current_key_index[0]] if current_key_index[0] < len(api_keys) else None

    def _next_key():
        from app.services.alert_service import create_alert
        from app.models.alert import AlertType, AlertSeverity
        exhausted_key = api_keys[current_key_index[0]]
        create_alert(
            type=AlertType.key_exhausted,
            severity=AlertSeverity.warning,
            title="HasData key exhausted — rotating to next",
            message=f"Key ...{exhausted_key[-8:]} returned credits-exhausted on Indeed scrape.",
            source="Indeed",
        )
        current_key_index[0] += 1
        if current_key_index[0] < len(api_keys):
            new_key = api_keys[current_key_index[0]]
            print(f"[Indeed] Switching to API key #{current_key_index[0] + 1}")
            create_alert(
                type=AlertType.key_rotated,
                severity=AlertSeverity.info,
                title=f"Switched to HasData key #{current_key_index[0] + 1}",
                message=f"Now using key ...{new_key[-8:]} for Indeed scraping.",
                source="Indeed",
            )
            return True
        print("[Indeed] All API keys exhausted")
        create_alert(
            type=AlertType.key_exhausted,
            severity=AlertSeverity.error,
            title="All HasData keys exhausted — Indeed scraping stopped",
            message="All configured HasData API keys have run out of credits. Add or top up keys in Platform settings.",
            source="Indeed",
        )
        return False

    def _request(url: str) -> dict:
        """Make a HasData request, rotating key on 402/403/429."""
        while True:
            key = _get_key()
            if not key:
                return {}
            r = httpx.get(
                "https://api.hasdata.com/scrape/indeed/job",
                params={"url": url},
                headers={"x-api-key": key},
                timeout=30,
            )
            if r.status_code in (402, 403, 429):
                print(f"[Indeed] Key #{current_key_index[0] + 1} exhausted (HTTP {r.status_code}), trying next")
                if not _next_key():
                    return {}
                continue
            return r.json()


    kw_list = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    search_queries = kw_list[:6] if kw_list else ["wordpress developer", "shopify developer", "php developer"]

    # Country-specific Indeed base URLs — sc param filters to Remote only
    country_bases = (config or {}).get("country_bases", [
        ("US", "https://www.indeed.com/jobs?q={q}&l=remote&sc=0kf%3Aattr(DSQF7)%3B&sort=date"),
        ("UK", "https://uk.indeed.com/jobs?q={q}&l=remote&sc=0kf%3Aattr(DSQF7)%3B&sort=date"),
        ("CA", "https://ca.indeed.com/jobs?q={q}&l=remote&sc=0kf%3Aattr(DSQF7)%3B&sort=date"),
        ("AU", "https://au.indeed.com/jobs?q={q}&l=remote&sc=0kf%3Aattr(DSQF7)%3B&sort=date"),
        ("AE", "https://www.indeed.com/jobs?q={q}&l=remote&sc=0kf%3Aattr(DSQF7)%3B&sort=date&co=AE"),
    ])

    country_map = {"US": "United States", "UK": "United Kingdom", "CA": "Canada", "AU": "Australia", "AE": "United Arab Emirates"}

    def _parse_html(html: str, country_code: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []
        for anchor in soup.select("a[data-jk]"):
            jk = anchor.get("data-jk", "")
            title = anchor.get_text(strip=True)
            if not title or not jk:
                continue
            tile = anchor
            for _ in range(8):
                tile = tile.parent
                if tile.find(attrs={"data-testid": "company-name"}) or tile.find(class_="company_location"):
                    break
            company_el = tile.find(attrs={"data-testid": "company-name"})
            location_el = tile.find(attrs={"data-testid": "text-location"})
            company = company_el.get_text(strip=True) if company_el else ""
            location = location_el.get_text(strip=True) if location_el else ""

            # Skip if company name missing
            if not company:
                continue

            # Skip hybrid jobs — only keep fully remote
            loc_lower = location.lower()
            if "hybrid" in loc_lower or ("in " in loc_lower and "remote" not in loc_lower):
                continue

            jobs.append({
                "title": title,
                "company_name": company,
                "location": location or "Remote",
                "country": country_map.get(country_code),
                "job_url": f"https://www.indeed.com/viewjob?jk={jk}",
                "apply_url": f"https://www.indeed.com/viewjob?jk={jk}",
            })
        return jobs

    seen_jks = set()
    all_jobs = []

    for country_code, base_url in country_bases:
        for query in search_queries:
            if not _get_key():
                break
            url = base_url.format(q=query.replace(" ", "+"))
            try:
                data = _request(url)
                html_url = data.get("requestMetadata", {}).get("html")
                if not html_url:
                    print(f"[Indeed] No HTML for {country_code} / {query}")
                    continue
                for job in _parse_html(httpx.get(html_url, timeout=30).text, country_code):
                    jk = job["job_url"].split("jk=")[-1]
                    if jk not in seen_jks:
                        seen_jks.add(jk)
                        all_jobs.append(job)
            except Exception as e:
                print(f"[Indeed] Error {country_code} / {query}: {e}")

    print(f"[Indeed] Returning {len(all_jobs)} jobs across {len(country_bases)} countries")
    return all_jobs


def scrape_wellfound(url, keywords, config) -> list:
    """
    Wellfound via scrape.do (super=true bypasses Cloudflare).
    Token stored in scrape_config.scrapedo_token.
    Extracts jobs from Apollo cache embedded in __NEXT_DATA__ after JS render.
    """

    import json as _json

    cfg = config or {}
    token = cfg.get("scrapedo_token", "")
    if not token:
        print("[Wellfound] No scrape.do token — add scrapedo_token in scrape_config")
        return []

    kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]

    def _kw_match(kw: str, text: str) -> bool:
        if " " in kw:
            return kw in text
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))

    def _parse_apollo(html: str) -> list:
        """Extract JobListing objects from Apollo cache embedded in __NEXT_DATA__."""
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not match:
            return []
        try:
            nd = _json.loads(match.group(1))
        except Exception:
            return []
        apollo = nd.get("props", {}).get("pageProps", {}).get("apolloState", {}).get("data", {})

        jobs = []
        for k, v in apollo.items():
            if not isinstance(v, dict) or v.get("__typename") != "JobListing":
                continue
            if v.get("remote") is False:
                continue

            title = (v.get("title") or "").strip()
            slug = v.get("slug") or ""
            job_url = f"https://wellfound.com/jobs/{slug}" if slug else ""
            locations = v.get("locationNames") or ["Remote"]
            location = ", ".join(locations) if locations else "Remote"

            startup_ref = (v.get("startup") or {}).get("__ref", "")
            company = (apollo.get(startup_ref) or {}).get("name", "")

            if not title or not company:
                continue

            jobs.append({
                "title": title,
                "company_name": company,
                "location": location,
                "job_url": job_url,
                "apply_url": job_url,
            })
        return jobs

    search_queries = kw_list[:16] if kw_list else ["software developer", "web developer"]
    seen_ids = set()
    all_jobs = []

    for query in search_queries:
        print(f"[Wellfound] Searching: {query}")
        try:
            r = httpx.get(
                "https://api.scrape.do/",
                params={
                    "token": token,
                    "url": f"https://wellfound.com/jobs?q={query.replace(' ', '%20')}&remote=true",
                    "render": "true",
                    "super": "true",
                },
                timeout=60,
            )
            if r.status_code != 200:
                print(f"[Wellfound] scrape.do returned {r.status_code} for '{query}'")
                continue

            jobs = _parse_apollo(r.text)
            print(f"[Wellfound] {len(jobs)} jobs for '{query}'")

            for job in jobs:
                job_id = job["job_url"]
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                all_jobs.append(job)

        except Exception as e:
            print(f"[Wellfound] Error for '{query}': {e}")

    print(f"[Wellfound] Returning {len(all_jobs)} matched jobs")
    return all_jobs


def scrape_remotive(url, keywords, config) -> list:
    """
    Remotive public API — https://remotive.com/api/remote-jobs
    Free, no auth, returns jobs with tags + description.
    Fetches multiple categories and filters locally by keywords.
    """
    kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]

    def _kw_match(kw: str, text: str) -> bool:
        if " " in kw:
            return kw in text
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))

    categories = ["software-dev", "design", "devops-sysadmin", "product"]
    if config and isinstance(config, dict):
        categories = config.get("categories", categories)

    seen_ids = set()
    raw_jobs = []
    for cat in categories:
        try:
            r = httpx.get(
                f"https://remotive.com/api/remote-jobs?category={cat}&limit=100",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
                follow_redirects=True,
            )
            for j in r.json().get("jobs", []):
                if j["id"] not in seen_ids:
                    seen_ids.add(j["id"])
                    raw_jobs.append(j)
        except Exception as e:
            print(f"[Remotive] Error fetching category {cat}: {e}")

    print(f"[Remotive] {len(raw_jobs)} unique jobs across all categories")

    jobs = []
    for j in raw_jobs:
        title = (j.get("title") or "").strip()
        company = (j.get("company_name") or "").strip()
        tags = j.get("tags") or []
        location = j.get("candidate_required_location") or "Remote"
        desc_html = j.get("description") or ""
        description = re.sub(r"<[^>]+>", "", desc_html).strip()[:3000]
        job_url = j.get("url") or ""

        if not title:
            continue

        if kw_list:
            search_text = f"{title} {company} {' '.join(tags)} {description[:300]}".lower()
            if not any(_kw_match(kw, search_text) for kw in kw_list):
                continue

        pub_date_str = j.get("publication_date") or ""
        posted_at = _parse_pub_date(pub_date_str)

        jobs.append({
            "title": title,
            "company_name": company,
            "location": location,
            "job_url": job_url,
            "apply_url": job_url,
            "job_description": description or None,
            "posted_at": posted_at,
        })

    print(f"[Remotive] Returning {len(jobs)} matched jobs")
    return jobs


def scrape_bark(url, keywords, config) -> list:
    """
    Bark.com lead scraper — logs in with credentials from scrape_config,
    navigates to available requests, extracts client name, project description,
    location, and budget.

    scrape_config required fields:
      email    — your bark.com login email
      password — your bark.com password

    Optional:
      max_pages — how many pages of leads to scrape (default 3)
    """
    import asyncio
    from playwright.async_api import async_playwright

    cfg = config or {}
    email = cfg.get("email", "")
    password = cfg.get("password", "")
    max_pages = int(cfg.get("max_pages", 3))

    if not email or not password:
        print("[Bark] No credentials — add email/password to scrape_config")
        return []

    kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]

    def _kw_match(kw: str, text: str) -> bool:
        if " " in kw:
            return kw in text
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))

    async def _run():
        jobs = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = await ctx.new_page()

            try:
                # Log in
                await page.goto("https://www.bark.com/en/gb/login/", timeout=30000)
                await page.wait_for_timeout(2000)

                # Fill login form
                await page.fill('input[type="email"], input[name="email"]', email)
                await page.fill('input[type="password"], input[name="password"]', password)
                await page.click('button[type="submit"], .login-btn, button:has-text("Log in"), button:has-text("Sign in")')
                await page.wait_for_timeout(3000)

                if "login" in page.url:
                    print(f"[Bark] Login may have failed — still on {page.url}")

                print(f"[Bark] Logged in, now at {page.url}")

                # Navigate to available leads/requests
                leads_urls = [
                    "https://www.bark.com/en/gb/seller/requests/",
                    "https://www.bark.com/en/gb/pro/leads/",
                    "https://www.bark.com/en/gb/seller/leads/",
                ]
                for leads_url in leads_urls:
                    await page.goto(leads_url, timeout=20000)
                    await page.wait_for_timeout(2000)
                    if "login" not in page.url:
                        print(f"[Bark] Leads page: {page.url}")
                        break

                for page_num in range(max_pages):
                    await page.wait_for_timeout(1500)
                    content = await page.content()
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, "html.parser")

                    # Try multiple card selectors — bark.com has changed layout over time
                    cards = (
                        soup.select(".request-card")
                        or soup.select(".lead-card")
                        or soup.select("[data-request-id]")
                        or soup.select(".request-item")
                        or soup.select("article.request")
                        or soup.select(".bark-request")
                    )

                    print(f"[Bark] Page {page_num + 1}: found {len(cards)} lead cards")

                    if not cards:
                        # Try to extract from JSON embedded in page
                        import json as _json
                        scripts = soup.find_all("script", type="application/json")
                        for sc in scripts:
                            try:
                                data = _json.loads(sc.string or "")
                                requests_list = (
                                    data.get("requests") or data.get("leads")
                                    or data.get("props", {}).get("requests")
                                    or []
                                )
                                for req in requests_list:
                                    title = req.get("service") or req.get("title") or req.get("category", "")
                                    company = req.get("name") or req.get("buyer_name") or req.get("client_name", "")
                                    desc = req.get("description") or req.get("details") or req.get("brief", "")
                                    location = req.get("location") or req.get("area") or "United Kingdom"
                                    budget = req.get("budget") or req.get("budget_range") or ""
                                    req_url = req.get("url") or req.get("link") or ""
                                    if req_url and not req_url.startswith("http"):
                                        req_url = f"https://www.bark.com{req_url}"
                                    if title:
                                        jobs.append({
                                            "title": title,
                                            "company_name": company or "Bark Client",
                                            "location": location,
                                            "country": "United Kingdom",
                                            "job_description": desc[:2000] if desc else None,
                                            "job_url": req_url,
                                            "apply_url": req_url,
                                            "budget": budget,
                                        })
                            except Exception:
                                pass
                        if jobs:
                            break

                    for card in cards:
                        # Title — service category or request title
                        title_el = (
                            card.select_one(".request-title, .service-name, h3, h2, .category-name")
                        )
                        title = title_el.get_text(strip=True) if title_el else ""

                        # Client name
                        client_el = card.select_one(".buyer-name, .client-name, .name, [class*='buyer']")
                        company = client_el.get_text(strip=True) if client_el else "Bark Client"

                        # Description / brief
                        desc_el = card.select_one(".description, .brief, .request-description, .details, p")
                        description = desc_el.get_text(strip=True) if desc_el else ""

                        # Location
                        loc_el = card.select_one(".location, [class*='location'], .area")
                        location = loc_el.get_text(strip=True) if loc_el else "United Kingdom"

                        # Budget
                        budget_el = card.select_one(".budget, [class*='budget'], .price")
                        budget = budget_el.get_text(strip=True) if budget_el else ""

                        # Link to the request
                        link_el = card.select_one("a[href]")
                        req_url = link_el.get("href", "") if link_el else ""
                        if req_url and not req_url.startswith("http"):
                            req_url = f"https://www.bark.com{req_url}"

                        if not title:
                            continue

                        if kw_list:
                            search_text = f"{title} {description}".lower()
                            if not any(_kw_match(kw, search_text) for kw in kw_list):
                                continue

                        jobs.append({
                            "title": title,
                            "company_name": company,
                            "location": location,
                            "country": "United Kingdom",
                            "job_description": f"{description}\n\nBudget: {budget}".strip() if budget else description or None,
                            "job_url": req_url,
                            "apply_url": req_url,
                        })

                    # Next page
                    next_btn = await page.query_selector("a[rel='next'], .pagination-next, button:has-text('Next')")
                    if not next_btn:
                        break
                    await next_btn.click()

            except Exception as e:
                print(f"[Bark] Error: {e}")
            finally:
                await browser.close()

        return jobs

    try:
        result = asyncio.run(_run())
        print(f"[Bark] Returning {len(result)} leads")
        return result
    except Exception as e:
        print(f"[Bark] Fatal error: {e}")
        return []


def scrape_linkedin_apify(url, keywords, config) -> list:
    """
    LinkedIn Jobs via Apify actor: curious_coder/linkedin-jobs-scraper
    Runs the actor synchronously (waits for completion), then fetches dataset.

    scrape_config required:
      apify_token  — Apify API token (from apify.com → Settings → Integrations)

    scrape_config optional:
      actor        — Apify actor ID (default: curious_coder~linkedin-jobs-scraper)
      location     — LinkedIn location string (default: "Worldwide")
      job_type     — "F" full-time / "P" part-time / "C" contract (default: none)
      remote       — true/false filter (default: true)
      max_items    — max jobs to return per run (default: 100)
      date_posted  — "r86400" past 24h / "r604800" past week (default: past week)

    keywords in platform config are used as LinkedIn search queries.
    Multiple keywords → multiple actor runs (one per keyword), results merged.
    """
    import time as _time

    cfg = config or {}
    actor = cfg.get("actor", "curious_coder~linkedin-jobs-scraper")
    location = cfg.get("location", "Worldwide")
    max_items = int(cfg.get("max_items", 100))
    date_posted = cfg.get("date_posted", "r604800")  # past week
    remote_only = cfg.get("remote", True)
    max_team_size = cfg.get("max_team_size", 50)  # skip companies with > N employees; None = no limit
    if max_team_size is not None:
        max_team_size = int(max_team_size)

    # Build key list from scrape_config api_keys (same pattern as HasData)
    raw_keys = cfg.get("api_keys") or []
    api_keys = [k["key"] if isinstance(k, dict) else k for k in raw_keys if (k["key"] if isinstance(k, dict) else k)]

    # Fall back to single apify_token field or global settings
    if not api_keys:
        single = cfg.get("apify_token", "")
        if not single:
            try:
                from app.models.settings import GlobalSetting
                with SyncSessionLocal() as _db:
                    row = _db.query(GlobalSetting).filter(GlobalSetting.key == "apify_token").first()
                    single = row.value if row else ""
            except Exception:
                pass
        if single:
            api_keys = [single]

    if not api_keys:
        print("[LinkedIn/Apify] No Apify API keys configured — add them in Platforms → LinkedIn Jobs")
        return []

    current_key_index = [0]

    def _get_key():
        return api_keys[current_key_index[0]] if current_key_index[0] < len(api_keys) else None

    def _next_key():
        current_key_index[0] += 1
        if current_key_index[0] < len(api_keys):
            print(f"[LinkedIn/Apify] Switching to key #{current_key_index[0] + 1}")
            return True
        print("[LinkedIn/Apify] All Apify keys exhausted")
        return False

    kw_list = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    if not kw_list:
        kw_list = ["wordpress developer", "php developer", "shopify developer"]

    # Cap at max_keywords_per_run actor runs to avoid draining Apify credits.
    # Combine remaining keywords into the first search using OR syntax.
    max_runs = int(cfg.get("max_keywords_per_run", 3))
    if len(kw_list) > max_runs:
        # Join extra keywords into the first few slots as "kw1 OR kw2 OR ..."
        combined = " OR ".join(kw_list)
        kw_list = [combined]

    def _run_actor(search_query: str) -> list:
        """Start actor run and wait for completion, then return dataset items."""
        import urllib.parse as _up
        # Build a LinkedIn job search URL; curious_coder~linkedin-jobs-scraper expects urls[]
        params = {"keywords": search_query, "f_WT": "2" if remote_only else ""}
        if location and location.lower() != "worldwide":
            params["location"] = location
        if date_posted:
            params["f_TPR"] = date_posted
        search_url = "https://www.linkedin.com/jobs/search/?" + _up.urlencode({k: v for k, v in params.items() if v})
        run_input = {
            "urls": [search_url],
            "count": max(10, max_items),
        }


        # Start run — rotate key on quota errors
        start_r = None
        while True:
            key = _get_key()
            if not key:
                return []
            try:
                start_r = httpx.post(
                    f"https://api.apify.com/v2/acts/{actor}/runs",
                    params={"token": key},
                    json=run_input,
                    timeout=30,
                )
            except Exception as e:
                print(f"[LinkedIn/Apify] Failed to start run for '{search_query}': {e}")
                return []
            if start_r.status_code in (402, 429):
                print(f"[LinkedIn/Apify] Key #{current_key_index[0]+1} quota exceeded, trying next")
                if not _next_key():
                    return []
                continue
            break

        if start_r.status_code not in (200, 201):
            print(f"[LinkedIn/Apify] Actor start failed ({start_r.status_code}): {start_r.text[:200]}")
            return []

        run_id = start_r.json().get("data", {}).get("id")
        if not run_id:
            print(f"[LinkedIn/Apify] No run ID in response: {start_r.text[:200]}")
            return []

        print(f"[LinkedIn/Apify] Run started: {run_id} for '{search_query}'")

        active_key = _get_key()

        # Poll for completion (max 5 minutes)
        for attempt in range(60):
            _time.sleep(5)
            try:
                status_r = httpx.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    params={"token": active_key},
                    timeout=15,
                )
                status = status_r.json().get("data", {}).get("status", "")
            except Exception:
                continue

            if status == "SUCCEEDED":
                break
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                print(f"[LinkedIn/Apify] Run {run_id} ended with status: {status}")
                return []
        else:
            print(f"[LinkedIn/Apify] Run {run_id} timed out after 5 min")
            return []

        # Fetch dataset
        dataset_id = status_r.json().get("data", {}).get("defaultDatasetId")
        if not dataset_id:
            return []

        try:
            data_r = httpx.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                params={"token": active_key, "format": "json", "clean": "true"},
                timeout=30,
            )
            items = data_r.json()
            print(f"[LinkedIn/Apify] Got {len(items)} items for '{search_query}'")
            return items if isinstance(items, list) else []
        except Exception as e:
            print(f"[LinkedIn/Apify] Dataset fetch error: {e}")
            return []

    # Maps LinkedIn companySize strings to their upper-bound employee count
    _SIZE_UPPER = {
        "1-10": 10, "11-50": 50, "51-200": 200, "201-500": 500,
        "501-1000": 1000, "501-1,000": 1000,
        "1001-5000": 5000, "1,001-5,000": 5000,
        "5001-10000": 10000, "5,001-10,000": 10000,
        "10001+": 999999, "10,001+": 999999, "10000+": 999999,
    }

    def _company_size_upper(raw: str) -> int | None:
        """Return the upper bound employee count for a LinkedIn companySize string."""
        if not raw:
            return None
        clean = raw.strip().replace(" ", "").replace("\xa0", "")
        # Try direct lookup first
        for k, v in _SIZE_UPPER.items():
            if k.lower() in clean.lower():
                return v
        # Fallback: extract largest number
        nums = re.findall(r"[\d,]+", clean)
        if nums:
            try:
                return int(nums[-1].replace(",", ""))
            except ValueError:
                pass
        return None

    def _parse_item(item: dict) -> dict | None:
        title = (item.get("title") or item.get("jobTitle") or "").strip()
        company = (item.get("companyName") or item.get("company") or "").strip()
        if not title:
            return None

        # Skip non-remote jobs — check location, workType, AND description text
        location_raw = (item.get("location") or item.get("jobLocation") or "Remote").strip()
        if remote_only:
            loc_check = location_raw.lower()
            work_type = (item.get("workType") or "").lower()
            desc_check = (item.get("descriptionText") or item.get("descriptionHtml") or "").lower()[:2000]
            hybrid_in_desc = bool(re.search(r'\bhybrid\b', desc_check))
            onsite_in_desc = bool(re.search(r'\bon[\-\s]?site\b|\bin[\-\s]?office\b|\bin[\-\s]?person\b', desc_check))
            if "hybrid" in loc_check or "hybrid" in work_type or hybrid_in_desc:
                return None
            if "on-site" in loc_check or "on-site" in work_type or "onsite" in loc_check or onsite_in_desc:
                return None

        # Company size filter — actor returns companyEmployeesCount (int) or companySize (string range)
        employees_count = item.get("companyEmployeesCount")
        size_raw = item.get("companySize") or item.get("companySizeRange") or item.get("company_size") or ""
        if employees_count is not None:
            # Convert integer to LinkedIn-style range string for storage
            n = int(employees_count)
            if n <= 10:
                company_size_str = "1-10"
            elif n <= 50:
                company_size_str = "11-50"
            elif n <= 200:
                company_size_str = "51-200"
            elif n <= 500:
                company_size_str = "201-500"
            elif n <= 1000:
                company_size_str = "501-1,000"
            elif n <= 5000:
                company_size_str = "1,001-5,000"
            elif n <= 10000:
                company_size_str = "5,001-10,000"
            else:
                company_size_str = "10,001+"
            # Apply filter using direct int comparison
            if max_team_size is not None and n > max_team_size:
                return None
        else:
            company_size_str = size_raw.strip() if size_raw else None
            if max_team_size is not None and company_size_str:
                upper = _company_size_upper(company_size_str)
                if upper is not None and upper > max_team_size:
                    return None

        job_url = (item.get("jobUrl") or item.get("url") or item.get("link") or "").strip()
        apply_url = (item.get("applyUrl") or job_url).strip()
        desc_html = item.get("descriptionHtml") or item.get("description") or ""
        description = re.sub(r"<[^>]+>", " ", desc_html).strip()
        description = re.sub(r"\s{2,}", " ", description)[:3000]
        posted_raw = item.get("postedAt") or item.get("publishedAt") or item.get("listedAt") or ""
        posted_at = _parse_pub_date(str(posted_raw)) if posted_raw else None

        # Country from location
        loc_lower = location_raw.lower()
        country = None
        if "united states" in loc_lower or ", us" in loc_lower:
            country = "United States"
        elif "united kingdom" in loc_lower or ", uk" in loc_lower or ", gb" in loc_lower:
            country = "United Kingdom"
        elif "canada" in loc_lower:
            country = "Canada"
        elif "australia" in loc_lower:
            country = "Australia"
        elif "india" in loc_lower:
            country = "India"
        elif "pakistan" in loc_lower:
            country = "Pakistan"
        elif "worldwide" in loc_lower or "remote" in loc_lower:
            country = None

        return {
            "title": title,
            "company_name": company,
            "company_size": company_size_str,   # stored directly from LinkedIn data
            "location": location_raw,
            "country": country,
            "job_url": job_url,
            "apply_url": apply_url,
            "job_description": description or None,
            "posted_at": posted_at,
        }

    seen_urls: set = set()
    all_jobs = []

    for kw in kw_list:
        items = _run_actor(kw)
        for item in items:
            parsed = _parse_item(item)
            if not parsed:
                continue
            key = parsed["job_url"] or f"{parsed['title']}|{parsed['company_name']}"
            if key in seen_urls:
                continue
            seen_urls.add(key)
            all_jobs.append(parsed)

    print(f"[LinkedIn/Apify] Returning {len(all_jobs)} total unique jobs")
    return all_jobs


def scrape_wpremotework(url, keywords, config) -> list:
    """
    WP Remote Work (wpremotework.com) via WordPress RSS feed.
    Fetches multiple pages; dc:creator = company name; content:encoded = full description.
    config: { "max_pages": 5 }  (default 5 pages × 10 items = up to 50 jobs)
    """
    CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
    DC_NS = "http://purl.org/dc/elements/1.1/"

    cfg = config or {}
    max_pages = int(cfg.get("max_pages", 5))
    kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]

    def _kw_match(kw: str, text: str) -> bool:
        if " " in kw:
            return kw in text
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text))

    seen_links: set = set()
    raw_items = []

    for page in range(1, max_pages + 1):
        feed_url = f"https://wpremotework.com/feed/?paged={page}"
        try:
            r = httpx.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
            root = ET.fromstring(r.text)
            page_items = list(root.iter("item"))
            if not page_items:
                break
            for item in page_items:
                link = (item.findtext("link") or "").strip()
                if link and link not in seen_links:
                    seen_links.add(link)
                    raw_items.append(item)
        except Exception as e:
            print(f"[WPRemoteWork] Feed error page {page}: {e}")
            break

    print(f"[WPRemoteWork] {len(raw_items)} unique items across {max_pages} pages")

    jobs = []
    for item in raw_items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        company = (item.findtext(f"{{{DC_NS}}}creator") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        desc_html = item.findtext(f"{{{CONTENT_NS}}}encoded") or item.findtext("description") or ""
        description = re.sub(r"<[^>]+>", " ", desc_html).strip()
        description = re.sub(r"\s{2,}", " ", description)[:3000]

        # Categories as tags for keyword matching
        categories = [c.text or "" for c in item.findall("category")]
        cat_text = " ".join(categories).lower()

        if not title:
            continue

        if kw_list:
            search_text = f"{title} {company} {cat_text} {description[:300]}".lower()
            if not any(_kw_match(kw, search_text) for kw in kw_list):
                continue

        jobs.append({
            "title": title,
            "company_name": company,
            "location": "Remote",
            "country": None,
            "job_url": link,
            "apply_url": link,
            "job_description": description or None,
            "posted_at": _parse_pub_date(pub_date),
        })

    print(f"[WPRemoteWork] Returning {len(jobs)} matched jobs")
    return jobs


def scrape_custom(url, keywords, config) -> list:
    """Generic Playwright scraper for custom URLs."""
    if not url:
        return []
    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def _run():
            cfg = config or {}
            title_sel = cfg.get("title_selector", "h2")
            company_sel = cfg.get("company_selector", ".company")
            jobs = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                try:
                    await page.goto(url, timeout=25000)
                    await page.wait_for_timeout(2000)
                    titles = await page.query_selector_all(title_sel)
                    companies = await page.query_selector_all(company_sel)
                    for i, el in enumerate(titles[:20]):
                        title = (await el.inner_text()).strip()
                        company = (await companies[i].inner_text()).strip() if i < len(companies) else ""
                        if title:
                            jobs.append({"title": title, "company_name": company, "location": "Remote"})
                except Exception as e:
                    print(f"[Custom] {url}: {e}")
                finally:
                    await browser.close()
            return jobs

        return asyncio.run(_run())
    except Exception as e:
        print(f"[Custom] Error: {e}")
        return []


SCRAPERS = {
    "indeed": scrape_indeed,
    "linkedin": scrape_linkedin_apify,
    "weworkremotely": scrape_weworkremotely,
    "wellfound": scrape_wellfound,
    "shine": scrape_jobicy,
    "nauk": scrape_remoteok,
    "wordpress_jobs": scrape_wordpress_jobs,
    "wpremotework": scrape_wpremotework,
    "bark": scrape_bark,
    "custom": scrape_custom,
}


@celery_app.task(name="app.tasks.scraper.enrich_job_descriptions_task")
def enrich_job_descriptions_task():
    """
    Summarize existing long job descriptions using Claude Haiku.
    Runs on jobs that have raw descriptions (>200 chars) not yet summarized.
    Processes 100 jobs per run to stay within timeout.
    """
    from app.models.job import Job
    from app.services.ai_service import summarize_job_description
    from sqlalchemy import func

    with SyncSessionLocal() as db:
        # Find jobs with long descriptions (raw, not yet summarized — summaries are short)
        jobs = (
            db.query(Job)
            .filter(
                Job.job_description != None,
                Job.job_description != "",
                func.length(Job.job_description) > 200,
            )
            .limit(100)
            .all()
        )

        updated = 0
        for job in jobs:
            raw_desc = job.job_description or ""
            summary = summarize_job_description(job.title or "", job.company_name or "", raw_desc)
            if summary:
                job.job_description = summary
                updated += 1

        db.commit()
        print(f"[Enrich] Summarized {updated} job descriptions")
