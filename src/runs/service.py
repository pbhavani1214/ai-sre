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
from src.investigation.models import RUN_REQUIRED_KEYS, InvestigationResult, RegressionTest, RowFix, TraceStep
from src.investigation.service import investigate_evidence
from src.runs import insights, regression
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
            try:
                record.target_snapshot = insights.target_snapshot(conn, record.target_table, schema)
            except sqlite3.Error:
                record.target_snapshot = None  # evidence for the AI only; never blocks a run
            validate_run(record, schema, existing_keys(conn, record.target_table))
            if record.status == "LOADING":
                load_run(record, conn)
        finally:
            conn.close()
    return record


# --- AI investigation -------------------------------------------------------------------------

RUN_SYSTEM_PROMPT = """You are an AI Software Reliability Engineer. A user uploaded a CSV file to be appended to an
existing SQLite table, and it failed. Deterministic validation has ALREADY told the user WHAT is wrong: every failed
check and the rows and values involved are shown to them. Do not repeat that back. Your job is to add what
validation cannot:

1. WHY the values are wrong: the likely origin of each problem, grouped by cause.
2. WHAT exactly to change in the file: row-level fixes.
3. HOW to stop it happening again: prevention steps for whoever produces the file.

EVIDENCE
The JSON package holds the validation results and their evidence lines, the target schema, and evidence that
validation does not show:
- column_profiles: per uploaded column, the value shapes, the values that don't fit the column's usual shape
  (with their rows), integer ranges and gaps in them, value counts for low-cardinality columns, and
  case_only_mismatches (uploaded value -> the allowed value it matches ignoring case);
- failing_rows: the full uploaded rows named by failed checks (the rest of the file is only profiled);
- target_data: what the table already holds (row count; per column distinct count, min/max, common values);
- run_history: the earlier attempts this run retries (its retry chain) and what failed in each.
Row numbers are line numbers in the uploaded file; row 1 is the header, so the first data row is row 2.

RULES
1. The evidence is authoritative. Never contradict it and never invent rows, values, counts or errors.
2. Separate facts from interpretation: observed_facts restate evidence; causes, hypotheses and fixes interpret it.
3. Look for patterns: a prefix on an ID ("CUST-1016" among plain integers), a case difference from an allowed
   value, a value the target has never held, a duplicated row that looks like a repeated export, a gap in an
   ID sequence that a duplicate may belong in, blanks in a required column, the same failure in an earlier run.
4. Root cause: when the failures are explained by specific values in the file, root_cause_status is IDENTIFIED,
   even when there are several independent causes. The root cause is the likely ORIGIN of those values (for
   example "the exporting system prefixes IDs and does not normalise status case; one record was entered twice"),
   not a restatement of which checks failed. Use INCONCLUSIVE only when the evidence conflicts or is missing,
   for example a LOAD_FAILED run whose database error the evidence does not explain.
5. Row fixes: one entry per value to change or row to drop, using the actual values in failing_rows.
   - REPLACE only when the correct value follows from the evidence (strip a prefix to match the column's usual
     integer shape; upper-case a value that matches an allowed value ignoring case; use a missing ID in the
     sequence for a duplicate whose other values differ). suggested_value must satisfy the column's type,
     NOT NULL and CHECK rules and must not create a new duplicate.
   - DELETE_ROW for a row that duplicates another row's data (a repeated record), not merely its key.
   - NEEDS_DECISION when the right value cannot be known from the evidence (a missing name, a value with no
     matching allowed value, which of two different records keeps a UNIQUE value). suggested_value is null.
     Never invent personal data such as names or e-mail addresses.
   - confidence: HIGH when the evidence leaves one reasonable value, MEDIUM when it is the most likely of a few,
     LOW otherwise. evidence: the one evidence line ID the fix addresses, in square brackets.
6. Hypotheses: 2-3 genuinely different explanations of the origin (not rewordings of one another), each
   SUPPORTED, REJECTED or INCONCLUSIVE on the evidence. Do not mark one SUPPORTED just to reach a conclusion.
7. Prevention: concrete steps for the producer of the file or the process, not "improve guidance".
8. Nothing has been applied or re-validated; do not claim it has.

CITATIONS
Every entry in observed_facts, each hypothesis's evidence, each cause group's evidence, and root_cause_evidence
must begin with one or more evidence IDs in square brackets taken ONLY from "available_evidence", e.g.
"[validation.not_null.001] ...". Prefer the specific evidence line IDs (validation.<check>.NNN) and the dataset.*
IDs over summaries. Keep observed_facts to at most 6 entries.

OUTPUT
Respond with ONE JSON object and nothing else:
{
  "summary": "2-3 sentences: what went wrong and why, in plain language",
  "observed_facts": ["[evidence.id] fact", "..."],
  "hypotheses": [
    {"hypothesis": "string", "status": "SUPPORTED|REJECTED|INCONCLUSIVE",
     "evidence": ["[evidence.id] ...", "..."], "reasoning": "why this status"}
  ],
  "root_cause_status": "IDENTIFIED|INCONCLUSIVE",
  "root_cause": "the likely origin of the failures",
  "root_cause_evidence": ["[evidence.id] ...", "..."],
  "root_cause_reasoning": "string",
  "cause_groups": [
    {"title": "short name of the cause", "category": "SOURCE_FORMAT|DATA_ENTRY|DUPLICATE_RECORD|NEW_VALUE|EXISTING_DATA|OTHER",
     "explanation": "why these values are wrong", "checks": ["check_name"], "rows": [7],
     "evidence": ["[evidence.id] ..."]}
  ],
  "row_fixes": [
    {"row": 7, "column": "customer_id", "action": "REPLACE|DELETE_ROW|NEEDS_DECISION", "current_value": "CUST-1016",
     "suggested_value": "1016", "reason": "string", "confidence": "HIGH|MEDIUM|LOW",
     "evidence": "[validation.data_type_compatibility.001]"}
  ],
  "prevention": ["concrete step", "..."],
  "recommended_fix": "one paragraph: what to change in this file, then what to change upstream"
}"""

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


def build_run_context(record: RunRecord, history: list[RunRecord] | None = None) -> dict[str, Any]:
    """The evidence package for one run: what that run produced, plus bounded context validation doesn't show."""
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
    context = {
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
        "column_profiles": insights.column_profiles(record.upload, schema),
        "failing_rows": insights.failing_rows(record.upload, record.validation_results),
    }
    if record.target_snapshot is not None:
        context["target_data"] = record.target_snapshot
    chain = insights.run_history(record, history or [])
    if chain:
        context["run_history"] = chain
    return context


def _replace_step(result: InvestigationResult, stage: str, description: str) -> None:
    for step in result.investigation_trace:
        if step.stage == stage:
            step.description = description
            return
    result.investigation_trace.append(TraceStep(stage, description))


def investigate_run(record: RunRecord, provider: LLMProvider | None = None,
                    history: list[RunRecord] | None = None) -> InvestigationResult:
    """AI investigation of a failed upload run. The AI's row fixes are checked against the file here, and the
    regression test is generated from the target schema (not by the AI)."""
    result = investigate_evidence(build_run_context(record, history), provider, RUN_SYSTEM_PROMPT, RUN_REQUIRED_KEYS)
    schema = record.schema or {}

    fixes, warnings = insights.verify_row_fixes([vars(f) for f in result.row_fixes], record.upload, schema)
    result.row_fixes = [RowFix(**f) for f in fixes]
    result.evidence_warnings += warnings
    n_apply = len(insights.applicable_fixes(fixes))
    _replace_step(result, "remediation_generation",
                  f"The LLM suggested {len(fixes)} row fix(es) and {len(result.prevention)} prevention step(s). "
                  f"Each fix was checked against the file; {n_apply} can be applied to a suggested CSV, the rest "
                  "need a decision. Nothing has been applied.")

    name, code = regression.generate(schema, record.upload, record.validation_results, record.target_table,
                                     record.database_name or record.database_id or "the target database", record.run_id)
    result.regression_test = RegressionTest(name=name, description="", code=code)
    _replace_step(result, "regression_test_generation",
                  f"Regression test '{name}' generated from the discovered schema of {record.target_table} "
                  "(deterministic, not by the LLM). It has not been executed.")
    return result


def suggested_csv(record: RunRecord) -> tuple[str, int]:
    """(CSV text, number of fixes applied) from the run's latest investigation."""
    fixes = (record.investigation or {}).get("row_fixes") or []
    return insights.apply_row_fixes(record.upload, fixes), len(insights.applicable_fixes(fixes))
