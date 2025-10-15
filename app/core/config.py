from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Real Estate AI Agent"
    environment: str = "dev"
    log_level: str = "INFO"
    api_key: str | None = None
    agent_mode: str = "graph"  # "graph" | "react"

    # Mongo
    mongo_uri: str = "mongodb+srv://jareer:jareer@analyticssolution.p71qsfo.mongodb.net/"
    mongo_db: str = "realestate"

    # Placeholder for Composio and provider keys
    composio_api_key: str | None = None
    openai_api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


