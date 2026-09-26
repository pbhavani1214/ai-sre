"""In-memory run store. Runs are lost when the backend restarts."""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

MAX_RUNS = 50


@dataclass
class RunRecord:
    detail: dict[str, Any]  # the run as the API returns it (without the investigation)
    target: dict[str, Any]  # the target table's definition when the run started
    upload_profile: dict[str, Any]
    investigation: dict[str, Any] | None = field(default=None)

    @property
    def run_id(self) -> str:
        return self.detail["run_id"]

    def to_api(self) -> dict[str, Any]:
        return {**self.detail, "investigation": self.investigation}


def new_run_id() -> str:
    return "run_" + secrets.token_hex(6)


class RunStore:
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

    def list(self) -> list[RunRecord]:
        """Newest first."""
        with self._lock:
            return list(reversed(self._runs.values()))

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


store = RunStore()
