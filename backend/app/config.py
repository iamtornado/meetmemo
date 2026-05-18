from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "MeetMemo"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Database ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "meetmemo"
    DB_PASSWORD: str = "meetmemo"
    DB_NAME: str = "meetmemo"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def database_url_sync(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # --- Redis ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # --- Storage ---
    STORAGE_PATH: str = str(Path(__file__).parent.parent / "data" / "uploads")

    # --- CORS ---
    # Accept JSON array or comma-separated origins
    CORS_ORIGINS: str = "http://localhost:3001"

    @property
    def cors_origins_list(self) -> list[str]:
        val = self.CORS_ORIGINS.strip()
        if val.startswith("["):
            import json
            return json.loads(val)
        return [s.strip() for s in val.split(",") if s.strip()]

    # --- LDAP / AD ---
    LDAP_ENABLED: bool = False
    LDAP_SERVER: str = "ldap://localhost:389"
    LDAP_BASE_DN: str = "dc=example,dc=com"
    LDAP_BIND_DN: str = ""
    LDAP_BIND_PASSWORD: str = ""
    LDAP_USER_SEARCH_FILTER: str = "(sAMAccountName={})"
    LDAP_GROUP_MEMBER_FILTER: str = "(member={})"

    # --- OIDC ---
    OIDC_ENABLED: bool = False
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_DISCOVERY_URL: str = ""
    OIDC_SCOPE: str = "openid profile email"

    # --- ML ---
    MODEL_DOWNLOAD_SOURCE: str = "modelscope"  # "modelscope" or "huggingface"
    WHISPER_MODEL: str = "base"  # tiny, base, small, medium, large-v3
    WHISPER_DEVICE: Literal["cpu", "cuda"] = "cpu"
    WHISPER_COMPUTE_TYPE: str = "auto"
    HF_TOKEN: str = ""  # Required only for HuggingFace + pyannote

    # --- ASR Provider ---
    ASR_PROVIDER: Literal["faster-whisper", "sensevoice"] = "faster-whisper"
    SENSEVOICE_MODE: Literal["local", "remote"] = "local"
    SENSEVOICE_API_URL: str = ""

    # --- Diarization Provider ---
    DIARIZE_PROVIDER: Literal["local", "remote"] = "local"
    DIARIZE_API_URL: str = ""

    # --- LLM ---
    LLM_PROVIDER: Literal["ollama", "openai", "litellm"] = "ollama"
    LLM_MODEL: str = "llama3"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_PROXY_URL: str = ""  # LiteLLM proxy URL, e.g. "http://litellm:4000"
    SUMMARY_TEMPLATE: str = ""

    # --- Celery ---
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB + 1}"


settings = Settings()

# Ensure storage path exists
os.makedirs(settings.STORAGE_PATH, exist_ok=True)
