from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def ensure_dirs(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def write_table(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        try:
            df.to_parquet(path, index=False)
            return path
        except Exception:
            fallback = path.with_suffix(".csv")
            df.to_csv(fallback, index=False, encoding="utf-8-sig")
            return fallback
    if path.suffix == ".jsonl":
        df.to_json(path, orient="records", lines=True, force_ascii=False)
        return path
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def read_table(path: Path) -> pd.DataFrame:
    if path.exists() and path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.exists() and path.suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    if path.exists():
        return pd.read_csv(path, dtype=str)
    parquet = path.with_suffix(".parquet")
    if parquet.exists():
        return pd.read_parquet(parquet)
    csv = path.with_suffix(".csv")
    if csv.exists():
        return pd.read_csv(csv, dtype=str)
    raise FileNotFoundError(path)
