from app.models.user import User, UserPermission
from app.models.profile import Profile, ProfileSkill, ProfileCV, ProfileEmail
from app.models.platform import Platform
from app.models.job import Job, JobContact
from app.models.application import Application, ApplicationFollowup
from app.models.lead import Lead, LeadActivity
from app.models.email_template import EmailTemplate
from app.models.email_account import EmailAccount
from app.models.settings import GlobalSetting

__all__ = [
    "User", "UserPermission",
    "Profile", "ProfileSkill", "ProfileCV", "ProfileEmail",
    "Platform",
    "Job", "JobContact",
    "Application", "ApplicationFollowup",
    "Lead", "LeadActivity",
    "EmailTemplate",
    "EmailAccount",
    "GlobalSetting",
]
