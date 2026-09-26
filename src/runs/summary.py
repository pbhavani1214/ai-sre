"""Build the contract's RunSummary for an uploaded run."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.runs.store import RunRecord
from src.validation.suite import _records

PREVIEW_ROWS = 20
SAMPLE_VALUES = 3


def _dataset(file_name: str, df: pd.DataFrame) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "row_count": len(df),
        "columns": [
            {
                "name": col,
                "non_null_count": int(df[col].notna().sum()),
                "sample_values": df[col].dropna().drop_duplicates().head(SAMPLE_VALUES).tolist(),
            }
            for col in df.columns
        ],
        "preview": _records(df.head(PREVIEW_ROWS)),
    }


def summarize(record: RunRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "created_at": record.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": _dataset(record.source_name, record.source),
        "target": _dataset(record.target_name, record.target),
        "pipeline_run": record.pipeline_run,
    }
