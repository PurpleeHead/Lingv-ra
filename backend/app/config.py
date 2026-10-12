from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./lingvera.db"
    auth_mode: str = "dev"
    telegram_bot_token: SecretStr | None = None
    mini_app_url: str = "http://localhost:5173"
    cors_allowed_origins: str = ""
    telegram_initdata_max_age_seconds: int = Field(default=3600, ge=30, le=3600)
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def empty_token_is_missing(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def enforce_deployment_auth(self):
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test or production")
        if self.auth_mode not in {"dev", "telegram"}:
            raise ValueError("AUTH_MODE must be 'dev' or 'telegram'")
        if self.auth_mode == "dev" and self.app_env != "development":
            raise ValueError(
                "Development identity is only available with APP_ENV=development"
            )
        if (
            self.telegram_bot_token is not None
            and not self.telegram_bot_token.get_secret_value().strip()
        ):
            raise ValueError("TELEGRAM_BOT_TOKEN cannot be empty")
        if self.app_env == "production":
            if self.auth_mode != "telegram" or self.telegram_bot_token is None:
                raise ValueError(
                    "Production requires AUTH_MODE=telegram and TELEGRAM_BOT_TOKEN"
                )
            if not self.mini_app_url.startswith("https://"):
                raise ValueError("Production MINI_APP_URL must use HTTPS")
        elif self.auth_mode == "telegram" and self.telegram_bot_token is None:
            raise ValueError("Telegram auth requires TELEGRAM_BOT_TOKEN")
        return self


settings = Settings()
