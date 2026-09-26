"""The upload pipeline: parse -> schema_check -> validate -> load, into an existing SQLite table.

Every rule comes from the target table's own definition (columns, NOT NULL, types, PRIMARY
KEY / UNIQUE keys and CHECK constraints). The CHECK expressions are evaluated by SQLite itself,
over a TEMP copy of the uploaded rows, so the pipeline never re-implements them. The load is
all-or-nothing: one transaction, attempted only if every check passes, rolled back on any
database error. Each stage writes real log lines and per-row issues, which become the evidence
for the AI investigation.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.runs.ingest import ParsedUpload
from src.target.introspect import describe_table, quote, row_count
from src.validation.suite import MAX_EVIDENCE, CheckResult

PIPELINE_NAME = "upload_to_target"
PREVIEW_ROWS = 20
MAX_ROW_ISSUES = 500
TEMP_TABLE = "temp._upload_rows"
LINE_COL = "__line"

_INT_RE = re.compile(r"^[+-]?\d+$")
_REAL_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_write_lock = threading.Lock()  # one load into the target database at a time


@dataclass
class PipelineOutcome:
    detail: dict[str, Any]  # the run as the API returns it
    target: dict[str, Any]  # the target table's definition when the run started
    upload_profile: dict[str, Any]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt(v: Any) -> str:
    return "NULL" if v is None else repr(v) if isinstance(v, str) else str(v)


def _convert(value: str | None, aff: str) -> tuple[Any, bool]:
    """Convert a CSV string to the column's affinity. Returns (value, conforms)."""
    if value is None:
        return None, True
    if aff == "INTEGER":
        return (int(value), True) if _INT_RE.match(value) else (value, False)
    if aff == "REAL":
        return (float(value), True) if _REAL_RE.match(value) else (value, False)
    if aff == "NUMERIC":
        if _INT_RE.match(value):
            return int(value), True
        if _REAL_RE.match(value):
            return float(value), True
    return value, True


class _Log:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, level: str, stage: str, message: str) -> None:
        self.lines.append(f"{_now():%H:%M:%S} {level:<5} {stage}: {message}")


def _check(name: str, severity: str, passed_summary: str, failed_summary: str, issues: list[dict],
           metrics: dict[str, Any] | None = None, evidence: list[str] | None = None) -> tuple[CheckResult, list[dict]]:
    """A CheckResult in the same format as the demo suite, plus its per-row issues."""
    for i in issues:
        i["check"] = name
    if evidence is None:
        evidence = [(f"line {i['line']}: " if i["line"] else "") + i["message"] for i in issues]
    total = len(evidence)
    evidence = evidence[:MAX_EVIDENCE]
    if total > len(evidence):
        evidence.append(f"... and {total - len(evidence)} more")
    affected = len({i["line"] for i in issues if i["line"]})
    result = CheckResult(name, "FAILED" if issues else "PASSED", severity,
                         failed_summary if issues else passed_summary,
                         {"affected_records": affected, **(metrics or {})}, evidence)
    return result, issues


def _key_text(cols: list[str], values: tuple) -> str:
    if len(cols) == 1:
        return f"{cols[0]}={_fmt(values[0])}"
    return f"({', '.join(cols)})=({', '.join(_fmt(v) for v in values)})"


# --- stages ------------------------------------------------------------------------------------

def _schema_check(target: dict, upload: ParsedUpload):
    table_cols = {c["name"]: c for c in target["columns"]}
    required = [c["name"] for c in target["columns"] if c["primary_key"] or (c["not_null"] and c["default"] is None)]
    missing = [c for c in required if c not in upload.columns]
    unknown = [c for c in upload.columns if c not in table_cols]
    issues = [{"line": None, "column": c, "value": None,
               "message": f"required column '{c}' ({table_cols[c]['type']}"
                          f"{' PRIMARY KEY' if table_cols[c]['primary_key'] else ' NOT NULL'}) is missing from the file"}
              for c in missing]
    issues += [{"line": None, "column": c, "value": None,
                "message": f"column '{c}' is not in table {target['name']} (its data would be lost)"} for c in unknown]
    return _check(
        "schema_columns", "HIGH",
        f"File columns match table {target['name']}",
        f"File columns don't match table {target['name']}: "
        f"{len(missing)} required column(s) missing, {len(unknown)} unknown column(s)",
        issues, {"missing_required_columns": len(missing), "unknown_columns": len(unknown)},
    ), missing


def _not_null(target: dict, upload: ParsedUpload):
    cols = [c["name"] for c in target["columns"]
            if (c["not_null"] or c["primary_key"]) and c["name"] in upload.columns]
    issues, per_col = [], {}
    for line, row in zip(upload.lines, upload.rows):
        for c in cols:
            if row[c] is None:
                per_col[c] = per_col.get(c, 0) + 1
                issues.append({"line": line, "column": c, "value": None,
                               "message": f"{c} is empty (the column is NOT NULL)"})
    return _check("not_null", "HIGH", "No empty values in required columns",
                  f"{len(issues)} empty value(s) in required columns", issues, {"null_values": per_col})


def _type_conformance(target: dict, upload: ParsedUpload, converted: list[dict]):
    typed = [c for c in target["columns"] if c["affinity"] in ("INTEGER", "REAL") and c["name"] in upload.columns]
    issues, per_col = [], {}
    for line, row, conv in zip(upload.lines, upload.rows, converted):
        for c in typed:
            if row[c["name"]] is not None and not conv[c["name"]][1]:
                per_col[c["name"]] = per_col.get(c["name"], 0) + 1
                issues.append({"line": line, "column": c["name"], "value": row[c["name"]],
                               "message": f"{c['name']}={_fmt(row[c['name']])} is not a valid {c['affinity']} "
                                          f"(column type {c['type']})"})
    return _check("type_conformance", "HIGH", "Every value matches its column type",
                  f"{len(issues)} value(s) don't match their column type", issues, {"invalid_values": per_col})


def _usable_keys(target: dict, upload: ParsedUpload) -> list[list[str]]:
    return [k for k in target["unique_keys"] if all(c in upload.columns for c in k)]


def _duplicate_keys(conn: sqlite3.Connection, target: dict, upload: ParsedUpload):
    issues, evidence, dup_keys, extra = [], [], 0, 0
    for key in _usable_keys(target, upload):
        cols = ", ".join(quote(c) for c in key)
        not_null = " AND ".join(f"{quote(c)} IS NOT NULL" for c in key)
        rows = conn.execute(
            f"SELECT {cols}, COUNT(*), group_concat({LINE_COL}) FROM {TEMP_TABLE} WHERE {not_null} "
            f"GROUP BY {cols} HAVING COUNT(*) > 1 ORDER BY MIN({LINE_COL})").fetchall()
        for r in rows:
            values, count = r[: len(key)], r[len(key)]
            lines = sorted(int(x) for x in r[-1].split(","))
            dup_keys += 1
            extra += count - 1
            text = _key_text(key, values)
            evidence.append(f"{text} appears {count} times in the file (lines {', '.join(map(str, lines))})")
            for ln in lines:
                others = ", ".join(str(o) for o in lines if o != ln)
                issues.append({"line": ln, "column": key[0], "value": values[0],
                               "message": f"{text} also appears on line(s) {others}"})
    return _check("duplicate_keys_in_file", "HIGH", "No duplicate key values within the file",
                  f"{dup_keys} key value(s) appear more than once in the file ({extra} extra row(s))",
                  issues, {"duplicate_keys": dup_keys, "extra_rows": extra}, evidence)


def _existing_conflicts(conn: sqlite3.Connection, target: dict, upload: ParsedUpload):
    issues, per_key = [], {}
    table = quote(target["name"])
    for key in _usable_keys(target, upload):
        cols = ", ".join(f"u.{quote(c)}" for c in key)
        on = " AND ".join(f"t.{quote(c)} = u.{quote(c)}" for c in key)
        rows = conn.execute(
            f"SELECT u.{LINE_COL}, {cols} FROM {TEMP_TABLE} u JOIN main.{table} t ON {on} "
            f"ORDER BY u.{LINE_COL}").fetchall()
        label = ", ".join(key)
        for r in rows:
            per_key[label] = per_key.get(label, 0) + 1
            issues.append({"line": r[0], "column": key[0], "value": r[1],
                           "message": f"{_key_text(key, r[1:])} already exists in table {target['name']} "
                                      f"(it must be unique)"})
    return _check("existing_key_conflicts", "HIGH", f"No key values already exist in table {target['name']}",
                  f"{len(issues)} key value(s) already exist in table {target['name']}",
                  issues, {"conflicts_by_key": per_key})


def _check_constraint(conn: sqlite3.Connection, target: dict, constraint: dict):
    name, expr = constraint["name"], constraint["expression"]
    involved = [c["name"] for c in target["columns"]
                if re.search(rf"(?<![\w\"]){re.escape(c['name'])}(?![\w\"])", expr, re.IGNORECASE)
                or f'"{c["name"]}"' in expr] or [c["name"] for c in target["columns"]]
    check_name = name if name.startswith("check_") else f"check_{name}"
    try:
        rows = conn.execute(
            f"SELECT {LINE_COL}, {', '.join(quote(c) for c in involved)} FROM {TEMP_TABLE} "
            f"WHERE NOT ({expr}) ORDER BY {LINE_COL}").fetchall()
    except sqlite3.Error as e:
        issue = {"line": None, "column": None, "value": None,
                 "message": f"CHECK ({expr}) could not be evaluated: {e}"}
        return _check(check_name, "MEDIUM", "", f"CHECK constraint {name} could not be evaluated", [issue])
    issues = []
    for r in rows:
        values = ", ".join(f"{c}={_fmt(v)}" for c, v in zip(involved, r[1:]))
        issues.append({"line": r[0], "column": involved[0], "value": r[1],
                       "message": f"{values} violates CHECK constraint {name}: CHECK ({expr})"})
    return _check(check_name, "MEDIUM", f"Every row satisfies CHECK constraint {name}",
                  f"{len(issues)} row(s) violate CHECK constraint {name}", issues, {"constraint": expr})


# --- entry point -------------------------------------------------------------------------------

def run_pipeline(db_path: str, table: str, upload: ParsedUpload, file_name: str, run_id: str,
                 retry_of: dict | None = None) -> PipelineOutcome:
    """Run every stage and return the run. Raises TargetNotFound if the table doesn't exist."""
    started = _now()
    log = _Log()
    with _write_lock:
        conn = sqlite3.connect(db_path, isolation_level=None)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            target = describe_table(conn, table)
            return _run(conn, target, upload, file_name, run_id, retry_of, started, log)
        finally:
            conn.close()


def _run(conn, target, upload, file_name, run_id, retry_of, started, log) -> PipelineOutcome:
    n = len(upload.rows)
    table = target["name"]
    if retry_of:
        log("INFO", "run", f"retry of {retry_of['run_id']} (status {retry_of['status']}"
                           + (f", failed at {retry_of['failed_stage']}" if retry_of.get("failed_stage") else "") + ")")
    log("INFO", "parse", f"read {n} data row(s) and {len(upload.columns)} column(s) from {file_name}")
    steps = [{"name": "parse", "status": "SUCCESS", "rows_in": n, "rows_out": n}]

    # schema_check
    (schema_result, schema_issues), missing = _schema_check(target, upload)
    if schema_result.status == "FAILED":
        for i in schema_issues:
            log("ERROR", "schema_check", i["message"])
    else:
        log("INFO", "schema_check", f"file columns match table {table}")
    steps.append({"name": "schema_check", "status": "SUCCESS" if schema_result.status == "PASSED" else "FAILED",
                  "rows_in": n, "rows_out": n if not missing else 0})

    # validate: TEMP copy of the upload with every table column, typed by affinity
    affinities = {c["name"]: c["affinity"] for c in target["columns"]}
    converted = [{c: _convert(row.get(c), a) for c, a in affinities.items()} for row in upload.rows]
    table_cols = [c["name"] for c in target["columns"]]
    conn.execute(f"CREATE TEMP TABLE _upload_rows ({LINE_COL} INTEGER, {', '.join(quote(c) for c in table_cols)})")
    conn.executemany(
        f"INSERT INTO {TEMP_TABLE} VALUES ({', '.join('?' * (len(table_cols) + 1))})",
        [(line, *(conv[c][0] for c in table_cols)) for line, conv in zip(upload.lines, converted)],
    )
    checks = [(schema_result, schema_issues), _not_null(target, upload),
              _type_conformance(target, upload, converted), _duplicate_keys(conn, target, upload),
              _existing_conflicts(conn, target, upload)]
    checks += [_check_constraint(conn, target, c) for c in target["check_constraints"]]
    results = [r for r, _ in checks]
    issues = [i for _, row_issues in checks for i in row_issues]
    failed = [r for r in results if r.status == "FAILED"]
    row_checks = [r for r in results if r.name != "schema_columns"]
    for r in row_checks:
        if r.status == "FAILED":
            log("ERROR", "validate", f"{r.name}: {r.summary}")
    bad_lines = {i["line"] for i in issues if i["line"]}
    rows_ok = 0 if missing else n - len(bad_lines)
    row_failed = any(r.status == "FAILED" for r in row_checks)
    log("INFO" if not row_failed else "ERROR", "validate",
        f"{len(row_checks) - sum(r.status == 'FAILED' for r in row_checks)} of {len(row_checks)} row checks "
        f"passed; {rows_ok} of {n} row(s) have no issues")
    steps.append({"name": "validate", "status": "FAILED" if row_failed else "SUCCESS", "rows_in": n,
                  "rows_out": rows_ok, "failed_checks": sum(r.status == "FAILED" for r in row_checks)})

    # load: all-or-nothing, only when every check passed
    before = target["row_count"]
    load_cols = [c for c in table_cols if c in upload.columns]
    load_error, loaded = None, 0
    if failed:
        log("WARN", "load", f"skipped: {len(failed)} check(s) failed, so no rows were written to {table}")
        steps.append({"name": "load", "status": "SKIPPED", "rows_in": rows_ok, "rows_written": 0})
    else:
        cols = ", ".join(quote(c) for c in load_cols)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"INSERT INTO main.{quote(table)} ({cols}) SELECT {cols} FROM {TEMP_TABLE} ORDER BY {LINE_COL}")
            conn.execute("COMMIT")
            loaded = n
            log("INFO", "load", f"committed {n} row(s) into {table} in one transaction")
            steps.append({"name": "load", "status": "SUCCESS", "rows_in": n, "rows_written": n})
        except sqlite3.Error as e:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            load_error = f"{type(e).__name__}: {e}"
            log("ERROR", "load", f"database rejected the load ({load_error}); transaction rolled back, 0 rows written")
            steps.append({"name": "load", "status": "FAILED", "rows_in": n, "rows_written": 0, "error": load_error})
    after = row_count(conn, table)

    failed_stage = next((s["name"] for s in steps if s["status"] == "FAILED"), None)
    status = "SUCCESS" if failed_stage is None and loaded else "FAILED"
    finished = _now()
    log("INFO" if status == "SUCCESS" else "ERROR", "run",
        f"finished: status={status} rows_written={loaded} {table} rows {before} -> {after}")

    detail = {
        "run_id": run_id,
        "created_at": _iso(started),
        "status": status,
        "failed_stage": failed_stage,
        "target_table": table,
        "file_name": file_name,
        "retry_of": retry_of["run_id"] if retry_of else None,
        "row_count": n,
        "columns": upload.columns,
        "rows_loaded": loaded,
        "target_rows_before": before,
        "target_rows_after": after,
        "load_error": load_error,
        "validation_summary": {"total_checks": len(results), "passed_checks": len(results) - len(failed),
                               "failed_checks": len(failed)},
        "validation_results": [r.to_dict() for r in results],
        "row_issues": issues[:MAX_ROW_ISSUES],
        "row_issues_truncated": len(issues) > MAX_ROW_ISSUES,
        "retry_comparison": _compare(retry_of, results) if retry_of else None,
        "preview": upload.rows[:PREVIEW_ROWS],
        "pipeline_run": {
            "run_id": run_id,
            "pipeline": PIPELINE_NAME,
            "status": status,
            "started_at": _iso(started),
            "finished_at": _iso(finished),
            "config": {"target_table": table, "file_name": file_name, "load_mode": "all_or_nothing",
                       "retry_of": retry_of["run_id"] if retry_of else None},
            "steps": steps,
            "logs": log.lines,
        },
    }
    return PipelineOutcome(detail, target, _profile(upload))


def _compare(previous: dict, results: list[CheckResult]) -> dict:
    before = {r["name"] for r in previous["validation_results"] if r["status"] == "FAILED"}
    now = {r.name for r in results if r.status == "FAILED"}
    return {
        "previous_run_id": previous["run_id"],
        "previous_status": previous["status"],
        "resolved_checks": sorted(before - now),
        "still_failing_checks": sorted(before & now),
        "new_failing_checks": sorted(now - before),
    }


def _profile(upload: ParsedUpload) -> dict[str, Any]:
    """Bounded summary of the uploaded file: shape and null counts only, never raw rows."""
    return {
        "row_count": len(upload.rows),
        "columns": upload.columns,
        "null_counts": {c: sum(r[c] is None for r in upload.rows) for c in upload.columns},
    }
