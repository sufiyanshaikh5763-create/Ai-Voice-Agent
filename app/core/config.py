"""Application settings loaded from environment variables / .env."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Calling Backend"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_calling"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    pin_encryption_key: str = ""

    sarvam_api_key: str = ""
    sarvam_base_url: str = ""
    sarvam_webhook_secret: str = ""
    sarvam_legacy_shared_token_enabled: bool = True
    public_api_base_url: str = ""

    default_timezone: str = "Asia/Kolkata"
    cors_origins: str = ""
    rate_limit_enabled: bool = True

    upload_dir: str = "uploads"

    email_backend: str = "console"
    resend_api_key: str = ""
    mail_from: str = "Talkaor <no-reply@talkaor.tech>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "noreply@talkaor.com"
    require_email_verification: bool = True
    docs_enabled: bool = False

    superadmin_1_email: str = ""
    superadmin_1_password: str = ""
    superadmin_2_email: str = ""
    superadmin_2_password: str = ""
    superadmin_sync_passwords: bool = False

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            if self.jwt_secret_key.startswith("change-me") or len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be a strong secret (32+ chars) in production")
            if not self.pin_encryption_key:
                raise ValueError("PIN_ENCRYPTION_KEY must be configured in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
