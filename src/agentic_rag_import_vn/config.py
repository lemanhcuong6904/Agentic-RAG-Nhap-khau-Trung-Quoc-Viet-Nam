from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")

    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    project_root: Path = Path.cwd()
    raw_dir: Path = Path("data/raw")
    manifests_dir: Path = Path("data/manifests")
    interim_dir: Path = Path("data/interim")
    processed_dir: Path = Path("data/processed")
    curated_dir: Path = Path("data/curated")
    quarantine_dir: Path = Path("data/quarantine")
    indexes_dir: Path = Path("data/indexes")
    reports_dir: Path = Path("reports")
    parser_version: str = "mvp-0.2.0"

    enable_legal: bool = True
    enable_vnaccs: bool = True
    enable_hs: bool = False
    enable_tariff: bool = False
    enable_origin_psr: bool = False
    enable_statistics: bool = False

    require_evidence: bool = True
    agent_max_retries: int = 2

    llm_provider: str = "none"
    llm_model: str = ""
    openai_api_key: str = ""

    embedding_provider: str = "none"
    embedding_model: str = ""
    enable_dense_retrieval: bool = False
    enable_hybrid_retrieval: bool = False
    enable_reranker: bool = False

    def resolve_paths(self) -> "Settings":
        root = self.project_root
        for field in (
            "raw_dir",
            "manifests_dir",
            "interim_dir",
            "processed_dir",
            "curated_dir",
            "quarantine_dir",
            "indexes_dir",
            "reports_dir",
        ):
            value = getattr(self, field)
            if not value.is_absolute():
                setattr(self, field, root / value)
        return self


settings = Settings().resolve_paths()
