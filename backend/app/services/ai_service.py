"""
AI service — uses Groq (free) → OpenAI → Anthropic in priority order,
falls back to smart template rendering when none are configured.
"""
import random
import re
from app.core.config import settings

_GROQ_KEY = getattr(settings, "GROQ_API_KEY", None)
_USE_GROQ = bool(_GROQ_KEY and _GROQ_KEY not in ("your-groq-api-key", "", "None"))

_OPENAI_KEY = getattr(settings, "OPENAI_API_KEY", None)
_USE_OPENAI = bool(_OPENAI_KEY and _OPENAI_KEY not in ("your-openai-api-key", "", "None"))

_USE_AI = bool(
    settings.ANTHROPIC_API_KEY
    and settings.ANTHROPIC_API_KEY not in ("your-anthropic-api-key", "", "None")
)

if _USE_GROQ:
    from groq import Groq as _Groq
    _groq_client = _Groq(api_key=_GROQ_KEY)

if _USE_OPENAI:
    from openai import OpenAI as _OpenAI
    _openai_client = _OpenAI(api_key=_OPENAI_KEY)

if _USE_AI:
    import anthropic
    _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _ai_chat(prompt: str, max_tokens: int = 512, json_mode: bool = False) -> str | None:
    """Call the best available AI — Groq → OpenAI → Anthropic."""
    import json as _json
    if _USE_GROQ:
        try:
            kwargs = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = _groq_client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[AI] Groq error: {e}")
    if _USE_OPENAI:
        try:
            kwargs = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = _openai_client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[AI] OpenAI error: {e}")
    if _USE_AI:
        try:
            msg = _client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        except Exception as e:
            print(f"[AI] Claude error: {e}")
    return None


# ── Template fallback helpers ─────────────────────────────────────────────────

def _first_name(full_name: str | None) -> str:
    if not full_name:
        return ""
    return full_name.strip().split()[0]


def _top_skills(profile_skills: list[str], job_text: str, n: int = 3) -> list[str]:
    """Return the skills most relevant to the job (appear in title/description)."""
    job_lower = job_text.lower()
    scored = [(s, 1 if s.lower() in job_lower else 0) for s in profile_skills]
    scored.sort(key=lambda x: -x[1])
    return [s for s, _ in scored[:n]]


def _render_template(template: str, vars: dict) -> str:
    """Replace {{key}} or {key} placeholders — tolerates unknown placeholders."""
    # Handle {{key}} first (DB templates use double braces)
    def replace_double(m):
        key = m.group(1)
        return str(vars.get(key, m.group(0)))
    result = re.sub(r"\{\{(\w+)\}\}", replace_double, template)
    # Then handle {key}
    def replace_single(m):
        key = m.group(1)
        return str(vars.get(key, m.group(0)))
    return re.sub(r"\{(\w+)\}", replace_single, result)


_JOB_SUBJECTS = [
    "{role} at {company}",
    "Re: {role} opening",
    "{role} — quick question",
    "Your {role} listing",
]

_JOB_BODIES = [
    """{greeting}
I saw the {role} listing at {company} and thought I'd reach out. I've been working with {skills} for a while now and think I'd be a good fit. Happy to share more or jump on a quick call if that's easier. CV attached.
Thanks,
{name}""",

    """{greeting}
Came across the {role} role at {company} and wanted to drop you a note. I work primarily with {skills} and have hands-on experience delivering similar projects. I've attached my CV — would love to chat if there's a fit.
Best,
{name}""",

    """{greeting}
I noticed you're looking for a {role} at {company}. My background is in {skills} and I've been doing this kind of work for a few years. Would it be worth a quick 15-minute call? CV is attached.
Thanks,
{name}""",
]

_FOLLOWUP_SUBJECTS = [
    "Re: {original_subject}",
    "following up",
    "{role} — just checking in",
]

_FOLLOWUP_BODIES = [
    """{greeting}
Just following up on the email I sent last week about the {role} role. Wanted to make sure it didn't get lost. Still very interested — happy to chat whenever works for you.
Thanks,
{name}""",

    """{greeting}
Circling back on my earlier note about the {role} position. No worries if the timing isn't right. If it's still open and you'd like to connect, I'm available this week.
Best,
{name}""",

    """{greeting}
Last follow-up on the {role} role — I know inboxes get busy. If there's any interest, I'd love to connect. If not, totally understand and wish you well in the search.
Thanks,
{name}""",
]


# ── Public API ────────────────────────────────────────────────────────────────

def _extract_profile_vars(profile_skills: list[str], profile_bio: str = "", years_experience_override: int | None = None) -> dict:
    """
    Extract years_experience and field from profile.
    If years_experience_override is set, it is used as-is and AI is only called for the field.
    Falls back to sensible defaults if AI is unavailable.
    """
    field = None
    years_exp = str(years_experience_override) if years_experience_override is not None else None

    if profile_skills or profile_bio:
        try:
            import json as _json
            if years_exp is None:
                prompt = (
                    f"Skills: {', '.join(profile_skills)}\n"
                    f"Bio: {profile_bio[:400]}\n\n"
                    "Based on the above, extract:\n"
                    "1. years_experience: estimated years of professional experience as a plain number only (e.g. 5)\n"
                    "2. field: the professional field as a short noun phrase only "
                    "(e.g. 'Java backend development', 'full-stack web development'). "
                    "Do NOT include years or experience language in the field value.\n"
                    "Return JSON only: {\"years_experience\": \"X\", \"field\": \"...\"}"
                )
            else:
                prompt = (
                    f"Skills: {', '.join(profile_skills)}\n"
                    f"Bio: {profile_bio[:400]}\n\n"
                    "Based on the above, return the professional field as a short noun phrase only "
                    "(e.g. 'Java backend development', 'full-stack web development'). "
                    "Do NOT include years, numbers, or experience language — field name only.\n"
                    "Return JSON only: {\"field\": \"...\"}"
                )
            result = _ai_chat(prompt, max_tokens=60, json_mode=True)
            if result:
                data = _json.loads(result)
                if years_exp is None:
                    years_exp = str(data.get("years_experience", "several"))
                field = str(data.get("field", ", ".join(profile_skills[:2])))
        except Exception:
            pass

    return {
        "years_experience": years_exp or "several",
        "field": field or (", ".join(profile_skills[:2]) if profile_skills else "software development"),
    }


def generate_job_email(
    job_title: str,
    company_name: str,
    job_description: str,
    profile_name: str,
    profile_skills: list[str],
    template_subject: str,
    template_body: str,
    hiring_person_name: str = None,
    profile_bio: str = "",
    years_experience: int | None = None,
) -> dict:
    job_text = f"{job_title} {job_description}"
    top = _top_skills(profile_skills, job_text)
    skills_str = ", ".join(top) if top else ", ".join(profile_skills[:3])
    contact_name = _first_name(hiring_person_name) if hiring_person_name else None
    greeting = f"Dear {contact_name}," if contact_name else "Dear Hiring Manager,"

    # Build base vars — always used for template rendering
    profile_vars = _extract_profile_vars(profile_skills, profile_bio, years_experience_override=years_experience)
    vars = {
        "greeting": greeting,
        "name": contact_name or "Hiring Manager",
        "role": job_title,
        "company": company_name or "your company",
        "sender_name": profile_name,
        "skills": skills_str,
        "original_subject": f"Application for {job_title}",
        **profile_vars,
    }

    # Always render the DB template (primary path)
    if template_body and len(template_body) > 30:
        body = _render_template(template_body, vars)
        subject = _render_template(template_subject, vars)
        return {"subject": subject, "body": body}

    # No template — fall back to built-in variants
    body = random.choice(_JOB_BODIES).format(**vars)
    subject = f"Application for {job_title} — {profile_name}"
    return {"subject": subject, "body": body}


def generate_followup_email(
    original_subject: str,
    company_name: str,
    profile_name: str,
    followup_number: int,
    template_body: str,
    hiring_person_name: str = None,
) -> dict:
    if _USE_AI:
        greeting = f"Hi {_first_name(hiring_person_name)}," if hiring_person_name else "Hi,"
        prompt = f"""Write follow-up #{followup_number} for a job application.
Original subject: {original_subject}
Company: {company_name}
Applicant: {profile_name}
Template: {template_body}
Rules: max 80 words, start with {greeting}, natural tone.
Return JSON only: {{"subject": "...", "body": "..."}}"""
        try:
            import json
            msg = _client.messages.create(
                model="claude-sonnet-4-6", max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return json.loads(msg.content[0].text)
        except Exception:
            pass

    idx = min(followup_number - 1, len(_FOLLOWUP_BODIES) - 1)
    greeting = f"Hi {_first_name(hiring_person_name)}," if hiring_person_name else "Hi,"
    # Extract role from original subject
    role = original_subject.replace("Application for ", "").split(" — ")[0].split(" at ")[0]
    vars = {
        "greeting": greeting,
        "role": role,
        "company": company_name or "your company",
        "name": profile_name,
        "original_subject": original_subject,
    }
    body = _FOLLOWUP_BODIES[idx].format(**vars)
    subject = f"Re: {original_subject}"
    return {"subject": subject, "body": body}


_B2B_INDUSTRY_PITCH = {
    "E-Commerce": {
        "services": "custom Shopify/WooCommerce development, conversion optimisation, and e-commerce automation",
        "value": "We help online stores increase revenue through faster sites, smarter checkout flows, and automated order workflows.",
    },
    "SaaS / Tech": {
        "services": "product development, API integrations, automation, and DevOps support",
        "value": "We help SaaS startups ship features faster and reduce operational overhead through smart automation.",
    },
    "Healthcare / MedTech": {
        "services": "HIPAA-compliant web apps, patient portals, booking systems, and digital marketing",
        "value": "We help health-tech companies build secure, compliant digital products that improve patient experience.",
    },
    "Real Estate / PropTech": {
        "services": "property listing platforms, CRM integrations, lead generation websites, and digital marketing",
        "value": "We help real estate businesses attract more buyers and automate their lead nurturing process.",
    },
}

_B2B_DEFAULT_PITCH = {
    "services": "web development, mobile apps, automation, SEO, and digital marketing",
    "value": "We help startups grow digitally — from building your first product to scaling your online presence.",
}


def generate_b2b_email(
    company_name: str,
    industry: str,
    country: str,
    contact_name: str,
    template_subject: str,
    template_body: str,
    sender_name: str,
) -> dict:
    pitch = _B2B_INDUSTRY_PITCH.get(industry, _B2B_DEFAULT_PITCH)
    greeting = f"Hi {_first_name(contact_name)}," if contact_name else "Hi,"

    if _USE_AI or _USE_GROQ or _USE_OPENAI:
        prompt = f"""Write a personalised B2B cold outreach email from {sender_name} at Expandimo.

Expandimo is an IT services company offering: {pitch['services']}.
Value proposition: {pitch['value']}

Target:
- Company: {company_name}
- Industry: {industry}
- Country: {country}
- Contact: {contact_name or 'the founder'}

Template subject: {template_subject}
Template body: {template_body}

Rules:
- Start with: {greeting}
- Max 120 words
- Sound human and specific to their industry — not generic
- One clear CTA (15-minute call or quick reply)
- Sign off as {sender_name}, Expandimo
- Return JSON only: {{"subject": "...", "body": "..."}}"""
        try:
            import json
            result = _ai_chat(prompt, max_tokens=512, json_mode=True)
            if result:
                return json.loads(result)
        except Exception:
            pass

    # Template rendering fallback
    vars = {
        "greeting": greeting,
        "company": company_name,
        "industry": industry,
        "country": country,
        "contact": _first_name(contact_name) or "there",
        "sender": sender_name,
        "services": pitch["services"],
        "value": pitch["value"],
    }
    if template_body and len(template_body) > 30:
        body = _render_template(template_body, vars)
        subject = _render_template(template_subject, vars)
        return {"subject": subject, "body": body}

    body = f"""{greeting}

I came across {company_name} and wanted to reach out. {pitch['value']}

At Expandimo we specialise in {pitch['services']} — working specifically with {industry} startups in {country}.

Would a quick 15-minute call this week make sense?

Best,
{sender_name}
Expandimo"""
    subject = f"Helping {company_name} grow digitally — quick question"
    return {"subject": subject, "body": body}


def score_lead(company_name: str, industry: str, country: str, company_size: str, domain: str) -> dict:
    if _USE_AI:
        try:
            import json
            prompt = f"""Score this B2B lead for Expandimo (IT services) 0-100.
Company: {company_name}, Industry: {industry}, Country: {country}, Size: {company_size}, Domain: {domain}
Return JSON: {{"score": N, "breakdown": {{"country_score":N,"industry_score":N,"size_score":N,"domain_score":N}}, "reason": "..."}}"""
            msg = _client.messages.create(
                model="claude-sonnet-4-6", max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return json.loads(msg.content[0].text)
        except Exception:
            pass

    # Heuristic scoring
    country_scores = {"US": 25, "UK": 22, "CA": 20, "AU": 20, "DE": 18, "NL": 18, "SG": 17}
    industry_scores = {"ecommerce": 25, "technology": 23, "saas": 23, "retail": 20, "marketing": 18}
    cs = country_scores.get(country[:2].upper() if country else "", 12)
    ind = industry.lower() if industry else ""
    is_ = next((v for k, v in industry_scores.items() if k in ind), 12)
    score = min(100, cs + is_ + 15 + 10)
    return {"score": score, "breakdown": {"country_score": cs, "industry_score": is_, "size_score": 15, "domain_score": 10}, "reason": "Heuristic score based on country and industry"}


def modify_cv_for_job(cv_text: str, job_title: str, job_description: str, skills_to_add: list[str]) -> str:
    if _USE_AI:
        try:
            skills_str = ", ".join(skills_to_add) if skills_to_add else "relevant skills"
            prompt = f"""You are a professional CV writer. Tailor the CV below for a "{job_title}" application.

JOB DESCRIPTION:
{job_description[:3000]}

KEY SKILLS REQUIRED: {skills_str}

ORIGINAL CV:
{cv_text}

INSTRUCTIONS — make ALL of these changes:
1. PROFESSIONAL SUMMARY: Rewrite the summary (or add one if missing) to directly mention the job title and 2-3 of the most relevant skills from the job description.
2. SKILLS SECTION: Move the skills that match the job requirements to the top of the list. Add any missing key skills from the job description that the candidate plausibly has based on their experience.
3. EXPERIENCE BULLETS: For each role, add or rewrite 1-2 bullet points that highlight work most relevant to this job. Use the same keywords from the job description.
4. PROJECTS: If there is a Projects section, add or promote a project that is most similar to what this job requires. If no Projects section exists and the job description emphasises specific tech/domain, add a short "Relevant Project" section with one realistic project that matches.
5. Keep all original content (company names, dates, education). Do not fabricate employers or qualifications.
6. Return ONLY the full updated CV text — no commentary, no markdown fences."""
            msg = _client.messages.create(
                model="claude-sonnet-4-6", max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text
        except Exception:
            pass

    # No AI — return CV unchanged (still attached as-is)
    return cv_text


def summarize_job_description(title: str, company: str, raw_text: str) -> str | None:
    """Summarize a job description to 3-4 sentences using OpenAI or Claude."""
    if not raw_text or len(raw_text.strip()) < 50:
        return None

    prompt = f"""Summarize this job posting in 3-4 concise sentences. Include: what the role involves, key skills required, and any notable perks or requirements. Be factual, no fluff.

Job: {title} at {company}
Description:
{raw_text[:4000]}

Return only the summary, no headings or bullets."""

    result = _ai_chat(prompt, max_tokens=200)
    return result if result else raw_text[:300].strip()
