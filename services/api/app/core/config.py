from functools import lru_cache
from pathlib import Path
from pydantic import EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "14Digital Sales Outreach Agent"
    environment: str = "development"
    database_url: str = "sqlite:///./prospectsz.sqlite3"
    app_secret_key: str = "development-only-change-before-live-32chars"
    access_token_minutes: int = 480
    admin_email: EmailStr = "admin@14digital.co.uk"
    admin_password: str = "change-me-before-live"
    frontend_origin: str = "http://localhost:3000"
    upload_dir: Path = Path("/tmp/prospectsz-uploads")
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    companies_house_api_key: str | None = None
    serper_api_key: str | None = None
    brave_search_api_key: str | None = None
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None
    email_provider: str = "mock"
    email_from: str = "Haider Zaidi <haider@14digital.co.uk>"
    live_email_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    max_emails_per_day: int = Field(20, ge=0, le=500)
    data_retention_days: int = Field(365, ge=30, le=3650)
    default_timezone: str = "Europe/London"


@lru_cache
def get_settings() -> Settings:
    return Settings()
