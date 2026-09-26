"""Run lifecycle (CONTRACT.md, "Run Processing" and "Run Status")."""

from __future__ import annotations

from typing import Any

from src.runs.store import RunRecord, utc_now
from src.runs.validation import has_blocking_failure, validate_upload


def validate_run(record: RunRecord, schema: dict[str, Any]) -> RunRecord:
    """CREATED -> VALIDATING -> FAILED_VALIDATION, or LOADING when no check FAILED.

    Loading into the target table is not implemented yet, so a run that passes validation stops at
    LOADING with completed_at still null. It is never reported as SUCCEEDED, and nothing is written.
    """
    if record.status != "CREATED":
        raise ValueError(f"Run {record.run_id} is {record.status}; only a CREATED run can be validated.")
    record.set_status("VALIDATING")
    record.validation_results = validate_upload(schema, record.upload)
    if has_blocking_failure(record.validation_results):
        record.set_status("FAILED_VALIDATION")
        record.completed_at = utc_now()
    else:
        record.set_status("LOADING")
    return record
