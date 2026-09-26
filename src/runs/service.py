"""Run lifecycle (CONTRACT.md, "Run Processing", "Run Status", "Load Semantics", "AI Investigation").

    CREATED -> VALIDATING -> FAILED_VALIDATION
                          -> LOADING -> SUCCEEDED
                                     -> LOAD_FAILED

Nothing here knows about a particular table: rules and INSERT columns come from the discovered schema.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any

from src.ai.provider import LLMProvider
from src.investigation.models import InvestigationResult
from src.investigation.service import investigate_evidence
from src.runs.store import RunRecord, utc_now
from src.runs.validation import ExistingKeys, has_blocking_failure, is_null, type_rule, validate_upload
from src.target.discovery import discover_schema, quote

INVESTIGABLE = ("FAILED_VALIDATION", "LOAD_FAILED")
RETRYABLE = ("FAILED_VALIDATION", "LOAD_FAILED")
_load_lock = threading.Lock()  # validation against existing rows and the insert must not interleave


def existing_keys(conn: sqlite3.Connection, table: str) -> ExistingKeys:
    def lookup(columns: list[str]) -> set[tuple]:
        cols = ", ".join(quote(c) for c in columns)
        return set(conn.execute(f"SELECT {cols} FROM main.{quote(table)}").fetchall())
    return lookup


def validate_run(record: RunRecord, schema: dict[str, Any], existing: ExistingKeys | None = None) -> RunRecord:
    """CREATED -> VALIDATING -> FAILED_VALIDATION, or LOADING when no check FAILED. Never writes."""
    if record.status != "CREATED":
        raise ValueError(f"Run {record.run_id} is {record.status}; only a CREATED run can be validated.")
    record.set_status("VALIDATING")
    record.schema = schema
    record.validation_results = validate_upload(schema, record.upload, existing)
    if has_blocking_failure(record.validation_results):
        record.set_status("FAILED_VALIDATION")
        record.completed_at = utc_now()
    else:
        record.set_status("LOADING")
    return record


def _typed(value: str, rule: str | None) -> Any:
    """CSV text -> the value to insert. Empty is NULL; INTEGER/REAL were already validated."""
    if is_null(value):
        return None
    if rule == "INTEGER":
        return int(value)
    if rule == "REAL":
        return float(value)
    return value


def load_run(record: RunRecord, conn: sqlite3.Connection) -> RunRecord:
    """LOADING -> SUCCEEDED (all rows committed) or LOAD_FAILED (rolled back, nothing written). APPEND only."""
    if record.status != "LOADING":
        raise ValueError(f"Run {record.run_id} is {record.status}; only a LOADING run can be loaded.")
    upload, schema = record.upload, record.schema
    targets = [c for c in schema["columns"] if c["name"] in upload.columns]  # unexpected columns are not loaded
    idx = [upload.columns.index(c["name"]) for c in targets]
    rules = [type_rule(c["data_type"]) for c in targets]
    rows = [tuple(_typed(row[i], rule) for i, rule in zip(idx, rules)) for row in upload.rows]
    sql = (f"INSERT INTO main.{quote(record.target_table)} ({', '.join(quote(c['name']) for c in targets)}) "
           f"VALUES ({', '.join('?' * len(targets))})")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(sql, rows)
        conn.execute("COMMIT")
    except sqlite3.Error as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        record.load_error = f"{type(e).__name__}: {e}"
        record.set_status("LOAD_FAILED")
    else:
        record.load_result = {"rows_loaded": len(rows), "target_table": record.target_table}
        record.set_status("SUCCEEDED")
    record.completed_at = utc_now()
    return record


def execute_run(record: RunRecord, db_path: str) -> RunRecord:
    """Validate a CREATED run against the target, then load it if nothing FAILED."""
    with _load_lock:
        conn = sqlite3.connect(db_path, isolation_level=None)  # explicit BEGIN/COMMIT/ROLLBACK
        try:
            schema = discover_schema(conn, record.target_table)
            validate_run(record, schema, existing_keys(conn, record.target_table))
            if record.status == "LOADING":
                load_run(record, conn)
        finally:
            conn.close()
    return record


# --- AI investigation -------------------------------------------------------------------------

DESCRIPTION = (
    "A user uploaded the CSV file {file_name} to be appended to the existing SQLite table {table}. "
    "Deterministic validation checked the file against the table's schema and constraints, which were "
    "discovered from the database (see target_table): required columns, unexpected columns, column types, "
    "NOT NULL, PRIMARY KEY and UNIQUE keys (duplicates within the file and values already in the table), "
    "and CHECK constraints. Rows are loaded in one transaction only if no check FAILED; otherwise nothing is "
    "written. Row numbers in the evidence are line numbers in the uploaded file (row 1 is the header). "
    "The user fixes problems by correcting the CSV and retrying the run."
)


def _profile(record: RunRecord) -> dict[str, Any]:
    """Bounded summary of the uploaded file: shape and empty-cell counts only, never raw rows."""
    upload = record.upload
    return {"row_count": upload.row_count, "columns": upload.columns,
            "null_counts": {c: sum(is_null(r[i]) for r in upload.rows) for i, c in enumerate(upload.columns)}}


def build_run_context(record: RunRecord) -> dict[str, Any]:
    """The evidence package for one run: only what that run produced."""
    summary = record.to_summary()
    stages = [{"name": "ingest", "status": "SUCCESS", "rows_in": record.upload.row_count,
               "rows_out": record.upload.row_count}]
    if "VALIDATING" in record.status_history:
        stages.append({"name": "validate", "status": "FAILED" if record.status == "FAILED_VALIDATION" else "SUCCESS",
                       "checks_failed": summary["summary"]["checks_failed"]})
    if "LOADING" in record.status_history:
        stages.append({"name": "load", "status": "FAILED" if record.status == "LOAD_FAILED" else "SUCCESS",
                       "rows_written": (record.load_result or {}).get("rows_loaded", 0),
                       **({"error": record.load_error} if record.load_error else {})})
    schema = record.schema or {}
    return {
        "pipeline_name": f"Load {record.file_name} into {record.target_table}",
        "pipeline_description": DESCRIPTION.format(file_name=record.file_name, table=record.target_table),
        "execution_evidence": {
            "execution_summary": {
                "run_id": record.run_id, "parent_run_id": record.parent_run_id, "run_status": record.status,
                "target_table": record.target_table, "file_name": record.file_name, **summary["summary"],
                "load_error": record.load_error,
            },
            "pipeline_run": {"run_id": record.run_id, "status": record.status, "steps": stages,
                             "status_history": record.status_history},
        },
        "validation_results": record.validation_results,
        "target_table": {"table_name": record.target_table, "columns": schema.get("columns", []),
                         "constraints": schema.get("constraints", [])},
        "upload": _profile(record),
    }


def investigate_run(record: RunRecord, provider: LLMProvider | None = None) -> InvestigationResult:
    return investigate_evidence(build_run_context(record), provider)
