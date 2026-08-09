from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from agentic_rag_import_vn.config import settings
from agentic_rag_import_vn.io_utils import ensure_dirs, write_table


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run(stage: str, inputs: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "run_id": str(uuid4()),
        "stage": stage,
        "status": "started",
        "started_at": utc_now(),
        "finished_at": None,
        "parser_version": settings.parser_version,
        "inputs": inputs or {},
    }


def finish_run(run: dict[str, object], status: str = "success", metrics: dict[str, object] | None = None) -> dict[str, object]:
    run = dict(run)
    run["status"] = status
    run["finished_at"] = utc_now()
    run["metrics"] = metrics or {}
    return run


def append_manifest_records(path: Path, records: list[dict[str, object]]) -> Path:
    ensure_dirs([path.parent])
    if not records:
        return path
    incoming = pd.DataFrame(records)
    if path.exists():
        try:
            existing = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, dtype=str)
            incoming = pd.concat([existing, incoming], ignore_index=True)
        except Exception:
            pass
    return write_table(incoming, path)


def write_processing_run(run: dict[str, object]) -> Path:
    return append_manifest_records(settings.manifests_dir / "processing_runs.parquet", [run])


def write_events(events: list[dict[str, object]]) -> Path:
    return append_manifest_records(settings.manifests_dir / "pipeline_events.parquet", events)
