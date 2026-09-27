from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UTM_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./utm-tracker.db"
    # Public base for short links, e.g. https://go.example.com
    base_url: str = "http://localhost:8000"
    # Salt for the daily visitor hash. Set a long random value in production.
    visitor_secret: str = "change-me"  # noqa: S105


@lru_cache
def get_settings() -> Settings:
    return Settings()
