"""In-memory store of uploaded runs. Lost on restart by design (see docs/implementation/README.md)."""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

MAX_RUNS = 20


@dataclass
class RunRecord:
    run_id: str
    created_at: datetime  # UTC
    source_name: str
    target_name: str
    source: pd.DataFrame  # full data; Phase 2 validates it
    target: pd.DataFrame
    pipeline_run: dict | None


def new_run_id() -> str:
    return "run_" + secrets.token_hex(6)


class RunStore:
    """Thread-safe, insertion-ordered; adding past max_runs evicts the oldest run."""

    def __init__(self, max_runs: int = MAX_RUNS):
        self.max_runs = max_runs
        self._runs: OrderedDict[str, RunRecord] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, record: RunRecord) -> None:
        with self._lock:
            self._runs[record.run_id] = record
            while len(self._runs) > self.max_runs:
                self._runs.popitem(last=False)

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


store = RunStore()


def get_run_store() -> RunStore:
    """FastAPI dependency; tests override it."""
    return store
