"""Deterministic, target-aware validation of an uploaded CSV (CONTRACT.md, "Validation Rules").

Every rule is derived from the target schema discovered from SQLite (src/target/discovery.py):
column names, declared types, nullability, primary key, UNIQUE keys and CHECK allowed values.
Nothing here knows about any particular table. The engine only reads: it never writes to the
target database, and it never changes the uploaded values.

Results use the contract's ValidationResult shape. Evidence lines start with an ID
`[validation.<check>.<NNN>]`, are ordered by file row, and are capped at MAX_EVIDENCE per check.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from src.runs.ingest import ParsedUpload

MAX_EVIDENCE = 5
CHECK_NAMES = (
    "required_columns",
    "unexpected_columns",
    "data_type_compatibility",
    "not_null",
    "primary_key_uniqueness",
    "unique_constraints",
    "check_constraints",
)

_INTEGER = re.compile(r"^[+-]?\d+$")
_REAL = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_SEVERITY = {"PASSED": "INFO", "SKIPPED": "INFO", "WARNING": "WARNING", "FAILED": "ERROR"}


def type_rule(declared_type: str) -> str | None:
    """Which contract type rule applies to a declared SQLite type (by SQLite's affinity rules).

    INTEGER and REAL values must parse as numbers; TEXT and any other type accept any value.
    """
    t = (declared_type or "").upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")) or not t or "BLOB" in t:
        return None
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return None


def conforms(value: str, rule: str | None) -> bool:
    if rule == "INTEGER":
        return bool(_INTEGER.match(value))
    if rule == "REAL":
        return bool(_REAL.match(value))
    return True


def is_null(value: str) -> bool:
    """A CSV cell has no null marker: an empty cell is the null value."""
    return value == ""


def _comparable(value: str, rule: str | None) -> Any:
    """How SQLite would compare the stored value: '101' and '0101' are the same INTEGER."""
    if rule == "INTEGER" and _INTEGER.match(value):
        return int(value)
    if rule == "REAL" and _REAL.match(value):
        return float(value)
    return value


def _fmt(value: str) -> str:
    return repr(value)


def _key_text(columns: list[str], values: list[str]) -> str:
    if len(columns) == 1:
        return f"{columns[0]}={_fmt(values[0])}"
    return f"({', '.join(columns)})=({', '.join(_fmt(v) for v in values)})"


def _rows_text(rows: list[int]) -> str:
    return f"row{'s' if len(rows) > 1 else ''} {', '.join(map(str, rows))}"


def _result(name: str, status: str, summary: str, metrics: dict[str, Any], observations: list[str]) -> dict[str, Any]:
    """Assign sequential evidence IDs and cap the evidence (the totals stay in metrics and summary)."""
    evidence = [f"[validation.{name}.{i:03d}] {text}" for i, text in enumerate(observations[:MAX_EVIDENCE], start=1)]
    return {"name": name, "status": status, "severity": _SEVERITY[status], "summary": summary,
            "metrics": metrics, "evidence": evidence}


class _Context:
    """The upload and schema, pre-indexed once for all checks."""

    def __init__(self, schema: dict[str, Any], upload: ParsedUpload):
        self.upload = upload
        self.columns = schema["columns"]
        self.by_name = {c["name"]: c for c in self.columns}
        self.constraints = schema["constraints"]
        self.with_default = set(schema.get("columns_with_default", []))
        self.position = {name: i for i, name in enumerate(upload.columns)}  # CSV column -> index
        self.rule = {c["name"]: type_rule(c["data_type"]) for c in self.columns}

    def present(self, column: str) -> bool:
        return column in self.position

    def cells(self, column: str):
        """(row number, raw value) for one uploaded column, in file order."""
        i = self.position[column]
        return zip(self.upload.lines, (row[i] for row in self.upload.rows))

    def keys(self, kind: str) -> list[list[str]]:
        return [c["columns"] for c in self.constraints if c["type"] == kind and c["columns"]]


# --- checks ----------------------------------------------------------------------------------

def check_required_columns(ctx: _Context) -> dict[str, Any]:
    """A column must be in the CSV if it's part of the primary key, or NOT NULL without a DEFAULT."""
    required = [c["name"] for c in ctx.columns
                if c["primary_key"] or (not c["nullable"] and c["name"] not in ctx.with_default)]
    missing = [name for name in required if not ctx.present(name)]
    observations = [f"required column `{name}` is missing from the CSV" for name in missing]
    return _result(
        "required_columns", "FAILED" if missing else "PASSED",
        f"{len(missing)} required column(s) missing: {', '.join(missing)}" if missing
        else f"All {len(required)} required column(s) are present",
        {"required_columns": len(required), "missing_columns": len(missing)}, observations,
    )


def check_unexpected_columns(ctx: _Context) -> dict[str, Any]:
    """CSV columns the target table doesn't have. A WARNING, not a failure (CONTRACT.md 8.2)."""
    unexpected = [name for name in ctx.upload.columns if name not in ctx.by_name]
    observations = [f"unexpected column `{name}` is not in the target table and would not be loaded"
                    for name in unexpected]
    return _result(
        "unexpected_columns", "WARNING" if unexpected else "PASSED",
        f"{len(unexpected)} unexpected column(s): {', '.join(unexpected)}" if unexpected
        else "Every CSV column exists in the target table",
        {"unexpected_columns": len(unexpected)}, observations,
    )


def _row_check(ctx: _Context, name: str, columns: list[str], bad: Callable[[str, str], str | None],
               passed: str, failed: str, empty_status: str = "PASSED", empty_summary: str = "") -> dict[str, Any]:
    """Run `bad(column, value)` on every cell of `columns`; it returns an observation or None."""
    if not columns:
        return _result(name, empty_status, empty_summary or passed, {"affected_rows": 0}, [])
    found: list[tuple[int, int, str]] = []  # (row, column order, observation)
    per_column: dict[str, int] = {}
    for order, column in enumerate(columns):
        for row, value in ctx.cells(column):
            observation = bad(column, value)
            if observation:
                found.append((row, order, f"{observation} at row {row}"))
                per_column[column] = per_column.get(column, 0) + 1
    found.sort()
    rows = {row for row, _, _ in found}
    return _result(name, "FAILED" if found else "PASSED",
                   failed.format(n=len(found), rows=len(rows)) if found else passed,
                   {"affected_rows": len(rows), "invalid_values": len(found), "by_column": per_column},
                   [text for _, _, text in found])


def check_data_type_compatibility(ctx: _Context) -> dict[str, Any]:
    typed = [c["name"] for c in ctx.columns if ctx.rule[c["name"]] and ctx.present(c["name"])]

    def bad(column: str, value: str) -> str | None:
        if is_null(value) or conforms(value, ctx.rule[column]):
            return None
        return f"{column}={_fmt(value)} is not a valid {ctx.rule[column]} (column type {ctx.by_name[column]['data_type']})"

    return _row_check(ctx, "data_type_compatibility", typed, bad,
                      "Every value is compatible with its column type",
                      "{n} value(s) in {rows} row(s) are not compatible with their column type",
                      empty_summary="No uploaded column has an INTEGER or REAL type")


def check_not_null(ctx: _Context) -> dict[str, Any]:
    required = [c["name"] for c in ctx.columns if not c["nullable"] and ctx.present(c["name"])]

    def bad(column: str, value: str) -> str | None:
        return f"`{column}` is empty (the column does not allow null)" if is_null(value) else None

    result = _row_check(ctx, "not_null", required, bad, "No empty values in columns that don't allow null",
                        "{n} empty value(s) in {rows} row(s) for columns that don't allow null")
    result["metrics"]["null_values"] = result["metrics"].pop("invalid_values", 0)
    return result


def _duplicates(ctx: _Context, name: str, keys: list[list[str]], label: str, no_keys: str) -> dict[str, Any]:
    """Duplicate key values within the upload, compared the way SQLite would compare them."""
    keys = [k for k in keys if all(ctx.present(c) for c in k)]
    if not keys:
        return _result(name, "SKIPPED", no_keys, {"affected_rows": 0, "duplicate_values": 0}, [])
    found: list[tuple[int, str]] = []
    rows_hit: set[int] = set()
    for key in keys:
        seen: dict[tuple, list[int]] = {}
        first_raw: dict[tuple, list[str]] = {}
        idx = [ctx.position[c] for c in key]
        for row, values in zip(ctx.upload.lines, ctx.upload.rows):
            raw = [values[i] for i in idx]
            if any(is_null(v) for v in raw):
                continue  # null keys are the not_null check's concern
            k = tuple(_comparable(v, ctx.rule[c]) for v, c in zip(raw, key))
            seen.setdefault(k, []).append(row)
            first_raw.setdefault(k, raw)
        for k, rows in seen.items():
            if len(rows) > 1:
                rows_hit.update(rows)
                found.append((rows[0], f"{_key_text(key, first_raw[k])} appears {len(rows)} times ({_rows_text(rows)})"))
    found.sort()
    return _result(name, "FAILED" if found else "PASSED",
                   f"{len(found)} duplicate {label} value(s) in the uploaded data" if found
                   else f"No duplicate {label} values in the uploaded data",
                   {"affected_rows": len(rows_hit), "duplicate_values": len(found)}, [t for _, t in found])


def check_primary_key_uniqueness(ctx: _Context) -> dict[str, Any]:
    keys = ctx.keys("PRIMARY_KEY")
    return _duplicates(ctx, "primary_key_uniqueness", keys, "primary key",
                       "The target has no primary key" if not keys else "Primary key column(s) are not in the CSV")


def check_unique_constraints(ctx: _Context) -> dict[str, Any]:
    keys = ctx.keys("UNIQUE")
    return _duplicates(ctx, "unique_constraints", keys, "UNIQUE",
                       "The target has no UNIQUE constraints" if not keys else "UNIQUE column(s) are not in the CSV")


def check_check_constraints(ctx: _Context) -> dict[str, Any]:
    checks = [c for c in ctx.constraints if c["type"] == "CHECK"]
    evaluable = {c["columns"][0]: c["allowed_values"] for c in checks
                 if c.get("allowed_values") is not None and len(c["columns"]) == 1 and ctx.present(c["columns"][0])}
    not_evaluated = [c["description"] for c in checks if c.get("allowed_values") is None]
    if not evaluable:
        reason = ("The target has no CHECK constraints" if not checks
                  else "No CHECK constraint could be evaluated: " + "; ".join(not_evaluated) if not_evaluated
                  else "The CHECK constraint column(s) are not in the CSV")
        return _result("check_constraints", "SKIPPED", reason, {"affected_rows": 0, "invalid_values": 0}, [])

    def bad(column: str, value: str) -> str | None:
        allowed = evaluable[column]
        if is_null(value) or value in allowed:  # NULL satisfies a CHECK in SQL
            return None
        return f"{column}={_fmt(value)} is not an allowed value ({', '.join(allowed)})"

    result = _row_check(ctx, "check_constraints", list(evaluable), bad,
                        "Every value satisfies the target's CHECK constraints",
                        "{n} value(s) in {rows} row(s) violate a CHECK constraint")
    if not_evaluated:
        result["summary"] += f" ({len(not_evaluated)} CHECK constraint(s) not evaluated: {'; '.join(not_evaluated)})"
        result["metrics"]["not_evaluated"] = len(not_evaluated)
    return result


CHECKS = [check_required_columns, check_unexpected_columns, check_data_type_compatibility, check_not_null,
          check_primary_key_uniqueness, check_unique_constraints, check_check_constraints]


def validate_upload(schema: dict[str, Any], upload: ParsedUpload) -> list[dict[str, Any]]:
    """All checks, in CHECK_NAMES order. Only a FAILED result blocks the load."""
    ctx = _Context(schema, upload)
    return [check(ctx) for check in CHECKS]


def has_blocking_failure(results: list[dict[str, Any]]) -> bool:
    return any(r["status"] == "FAILED" for r in results)
