"""
Seed or update B2B email templates in the database.
Run from backend/: python scripts/seed_b2b_templates.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SyncSessionLocal
from app.models.email_template import EmailTemplate, TemplateType

TEMPLATES = [
    {
        "template_type": TemplateType.b2b_initial,
        "name": "B2B Initial Outreach",
        "subject": "Quick question about {company}'s tech roadmap",
        "body": """Hi {name},

I came across {company} and was impressed by what you're building in the {industry} space.

I'm reaching out from Expandimo — we're an IT services company that helps {industry} startups scale their technology without the overhead of a full in-house team. We specialise in:

{services}

{value_prop}

Many of our clients started exactly where you are now — great product vision, limited engineering bandwidth. We've helped them ship faster and cut development costs by 30–50%.

Would you be open to a 15-minute call this week to see if there's a fit? I'm happy to share some examples relevant to {industry}.

Best regards,
{sender_name}
Expandimo | expandimo.com""",
        "is_default": True,
    },
    {
        "template_type": TemplateType.b2b_followup_1,
        "name": "B2B Follow-up #1 (Day 3)",
        "subject": "Re: Quick question about {company}'s tech roadmap",
        "body": """Hi {name},

Just circling back on my previous message — wanted to make sure it didn't get buried.

We work with {industry} companies like {company} to help them move faster on product and tech. Whether it's building out a new feature, scaling infrastructure, or filling a short-term gap in the team, we can plug in quickly without long onboarding cycles.

If now isn't the right time, no worries at all — just let me know and I'll follow up when timing is better.

Otherwise, happy to send over a few case studies if that would be helpful.

Best,
{sender_name}
Expandimo""",
        "is_default": True,
    },
    {
        "template_type": TemplateType.b2b_followup_2,
        "name": "B2B Follow-up #2 (Day 7)",
        "subject": "One thing that might be relevant for {company}",
        "body": """Hi {name},

I'll keep this short.

We recently helped a {industry} company in {country} cut their time-to-launch by 6 weeks by taking over their backend development while their internal team focused on product decisions.

If you're facing anything similar — tight deadlines, scaling challenges, or just need extra hands — I'd love to share how we approached it.

Worth a quick 15 minutes?

{sender_name}
Expandimo | expandimo.com""",
        "is_default": True,
    },
    {
        "template_type": TemplateType.b2b_followup_3,
        "name": "B2B Follow-up #3 (Day 14) — Final",
        "subject": "Last note from Expandimo",
        "body": """Hi {name},

I won't keep following up after this — I know inboxes get busy.

Just wanted to leave the door open: if {company} ever needs IT support, custom development, or tech consulting, we'd love to help. We work with {industry} companies across {country} and understand the specific challenges you face.

Feel free to reach out anytime at expandimo.com or reply to this email.

Wishing {company} continued success!

{sender_name}
Expandimo""",
        "is_default": True,
    },
]


def seed():
    with SyncSessionLocal() as db:
        for tpl_data in TEMPLATES:
            # Check if a default template of this type already exists
            existing = db.query(EmailTemplate).filter(
                EmailTemplate.template_type == tpl_data["template_type"],
                EmailTemplate.is_default == True,
            ).first()

            if existing:
                existing.name = tpl_data["name"]
                existing.subject = tpl_data["subject"]
                existing.body = tpl_data["body"]
                existing.is_active = True
                print(f"Updated: {tpl_data['template_type'].value}")
            else:
                template = EmailTemplate(
                    name=tpl_data["name"],
                    template_type=tpl_data["template_type"],
                    subject=tpl_data["subject"],
                    body=tpl_data["body"],
                    is_default=True,
                    is_active=True,
                )
                db.add(template)
                print(f"Created: {tpl_data['template_type'].value}")

        db.commit()
        print("Done.")


if __name__ == "__main__":
    seed()
