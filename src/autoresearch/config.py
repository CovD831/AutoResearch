from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = Field(default="offline", alias="LLM_PROVIDER")
    llm_api_key: SecretStr | None = Field(default=None, alias="LLM_API_KEY")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=60, alias="LLM_TIMEOUT_SECONDS")

    semantic_scholar_api_key: SecretStr | None = Field(
        default=None, alias="SEMANTIC_SCHOLAR_API_KEY"
    )
    semantic_scholar_timeout_seconds: float = Field(
        default=30, alias="SEMANTIC_SCHOLAR_TIMEOUT_SECONDS"
    )
    openalex_api_key: SecretStr | None = Field(default=None, alias="OPENALEX_API_KEY")
    openalex_mailto: str | None = Field(default=None, alias="OPENALEX_MAILTO")

    data_dir: Path = Field(default=Path("var"), alias="AUTORESEARCH_DATA_DIR")
    db_path: Path = Field(default=Path("var/autoresearch.sqlite3"), alias="AUTORESEARCH_DB_PATH")
    checkpoint_path: Path = Field(
        default=Path("var/checkpoints.sqlite3"), alias="AUTORESEARCH_CHECKPOINT_PATH"
    )
    projects_dir: Path = Field(default=Path("paper-projects"), alias="AUTORESEARCH_PROJECTS_DIR")
    template_dir: Path = Field(
        default=Path("paper-projects/_template"), alias="AUTORESEARCH_TEMPLATE_DIR"
    )
    network_enabled: bool = Field(default=False, alias="AUTORESEARCH_NETWORK_ENABLED")

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.llm_provider != "offline"
            and self.llm_api_key
            and self.llm_base_url
            and self.llm_model
        )

    @property
    def semantic_scholar_configured(self) -> bool:
        """ADR-01 slot 2 primary retrieval source needs a registered free key."""

        return bool(self.semantic_scholar_api_key)

    def ensure_runtime_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def safe_summary(self) -> dict[str, object]:
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_base_url_configured": bool(self.llm_base_url),
            "llm_api_key_configured": bool(self.llm_api_key),
            "semantic_scholar_api_key_configured": bool(self.semantic_scholar_api_key),
            "network_enabled": self.network_enabled,
            "db_path": str(self.db_path),
            "checkpoint_path": str(self.checkpoint_path),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
