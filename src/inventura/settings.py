"""Application settings from environment variables (prefix INVENTURA_) or a .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Defaults match docker-compose.yml, so local development needs no configuration.
LOCAL_DATABASE_URL = "postgresql+psycopg://inventura:inventura@localhost:5433/inventura"
LOCAL_TEST_DATABASE_URL = "postgresql+psycopg://inventura:inventura@localhost:5433/inventura_test"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INVENTURA_", env_file=".env", extra="ignore")

    database_url: str = LOCAL_DATABASE_URL
    test_database_url: str = LOCAL_TEST_DATABASE_URL
    column_mapping: Path = Path("config/column_mapping.yaml")
    max_upload_bytes: int = 20 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
