"""Runs and the in-memory run store (CONTRACT.md, "Run Storage": latest 20 runs, lost on restart)."""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.runs.ingest import ParsedUpload

MAX_RUNS = 20


def new_run_id() -> str:
    return "run_" + secrets.token_hex(6)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RunRecord:
    run_id: str
    target_id: str
    target_table: str
    file_name: str
    upload: ParsedUpload  # internal only; never returned by the API
    status: str = "CREATED"
    parent_run_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    load_result: dict[str, Any] | None = None
    investigation: dict[str, Any] | None = None  # latest AI investigation (RunInvestigateResponse)
    # Internal, never returned directly:
    status_history: list[str] = field(default_factory=list)  # every status the run has had
    schema: dict[str, Any] | None = None  # the target schema the run was validated against
    load_error: str | None = None  # the database error when the load failed
    database_id: str = ""  # the database the target table belongs to (a retry inherits it)

    def __post_init__(self):
        self.status_history.append(self.status)

    def set_status(self, status: str) -> None:
        self.status = status
        self.status_history.append(status)

    def to_summary(self) -> dict[str, Any]:
        """The contract's RunSummary."""
        passed = sum(r["status"] == "PASSED" for r in self.validation_results)
        failed = sum(r["status"] == "FAILED" for r in self.validation_results)
        return {
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "database_id": self.database_id,
            "target_id": self.target_id,
            "target_table": self.target_table,
            "file_name": self.file_name,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "summary": {
                "rows_received": self.upload.row_count,
                "checks_total": len(self.validation_results),
                "checks_passed": passed,
                "checks_failed": failed,
            },
            "validation_results": self.validation_results,
            "load_result": self.load_result,
            "investigation": self.investigation,
        }


class RunStore:
    """Thread-safe, insertion-ordered; adding past max_runs drops the oldest run."""

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

    def __len__(self) -> int:
        with self._lock:
            return len(self._runs)


store = RunStore()
