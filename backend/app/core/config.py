from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str
    SYNC_DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    GMAIL_CLIENT_ID: str
    GMAIL_CLIENT_SECRET: str
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/gmail/callback"

    # Legacy single-key fields (kept for backward compat)
    APOLLO_API_KEY: Optional[str] = None
    LUCA_API_KEY: Optional[str] = None
    # Multi-account comma-separated keys
    APOLLO_API_KEYS: Optional[str] = None   # e.g. "key1,key2,key3"
    LUSHA_API_KEYS: Optional[str] = None    # e.g. "key1,key2"
    HUNTER_API_KEYS: Optional[str] = None   # e.g. "key1,key2"
    HASDATA_API_KEY: Optional[str] = None

    APP_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    STORAGE_PATH: str = "/storage"
    TRACKING_PIXEL_URL: str = "http://localhost:8000/api/v1/track"

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()
