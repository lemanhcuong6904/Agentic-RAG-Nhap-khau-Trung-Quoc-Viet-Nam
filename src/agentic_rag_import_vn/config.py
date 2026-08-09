from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")

    project_root: Path = Path.cwd()
    raw_dir: Path = Path("data/raw")
    manifests_dir: Path = Path("data/manifests")
    interim_dir: Path = Path("data/interim")
    processed_dir: Path = Path("data/processed")
    indexes_dir: Path = Path("data/indexes")
    reports_dir: Path = Path("reports")
    parser_version: str = "mvp-0.1.0"

    def resolve_paths(self) -> "Settings":
        root = self.project_root
        for field in (
            "raw_dir",
            "manifests_dir",
            "interim_dir",
            "processed_dir",
            "indexes_dir",
            "reports_dir",
        ):
            value = getattr(self, field)
            if not value.is_absolute():
                setattr(self, field, root / value)
        return self


settings = Settings().resolve_paths()
