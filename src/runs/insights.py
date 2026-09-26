"""Evidence for the AI that the validation checks don't show, and deterministic handling of its row fixes.

Validation says WHAT is wrong with the uploaded file. To explain WHY and suggest corrections, the AI also gets:

- column_profiles: how each uploaded column's values usually look (value shapes, the values that don't fit
  the column's usual shape, integer ranges and gaps, low-cardinality value counts, case-only mismatches
  with a CHECK constraint's allowed values)
- target_data: a bounded snapshot of what the target table already holds, taken when the run was validated
- failing_rows: the full uploaded rows that failed checks (bounded; the rest of the file is only profiled)
- run_history: the earlier attempts this run retries (its retry chain), with what failed in each

The AI's suggested row fixes are checked here against the actual file, and applied here to build the
suggested corrected CSV. The AI never writes to the database: a corrected file goes through validation again.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from collections import Counter
from typing import Any

from src.runs.ingest import ParsedUpload
from src.runs.validation import conforms, is_null, type_rule
from src.target.discovery import quote

MAX_FAILING_ROWS = 25
MAX_OUTLIERS = 5
MAX_LISTED_VALUES = 10  # value counts are listed only for categorical columns (see _categorical)
MAX_SEQUENCE_SPAN = 200  # integer gaps are listed only for short ranges
MAX_HISTORY = 5
FIX_ACTIONS = ("REPLACE", "DELETE_ROW", "NEEDS_DECISION")
CONFIDENCE = ("HIGH", "MEDIUM", "LOW")

_INTEGER = re.compile(r"^[+-]?\d+$")
_DECIMAL = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")
_PREFIXED = re.compile(r"^[A-Za-z]+[-_ ]?\d+$")
_ROWS = re.compile(r"\brows? (\d+(?:, \d+)*)")


def value_shape(value: str) -> str:
    """A coarse description of what a raw CSV value looks like."""
    if is_null(value):
        return "empty"
    if _INTEGER.match(value):
        return "integer"
    if _DECIMAL.match(value):
        return "decimal"
    if _DATE.match(value):
        return "date"
    if _EMAIL.match(value):
        return "email"
    if _PREFIXED.match(value):
        return "letters+number"
    if value.isalpha():
        return "UPPERCASE word" if value.isupper() else "lowercase word" if value.islower() else "Capitalized word"
    return "text"


def _allowed_values(schema: dict[str, Any]) -> dict[str, list[str]]:
    return {c["columns"][0]: c["allowed_values"] for c in schema.get("constraints", [])
            if c["type"] == "CHECK" and c.get("allowed_values") is not None and len(c["columns"]) == 1}


def _key_columns(schema: dict[str, Any]) -> set[str]:
    return {col for c in schema.get("constraints", []) if c["type"] in ("PRIMARY_KEY", "UNIQUE") for col in c["columns"]}


def _categorical(distinct: int, count: int) -> bool:
    """Few distinct values that repeat (status, country), not identifiers or free text such as names or e-mails."""
    return 0 < distinct <= MAX_LISTED_VALUES and distinct * 2 <= count


def column_profiles(upload: ParsedUpload, schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Per uploaded column: value shapes, values that don't fit the usual shape, and hints for corrections."""
    by_name = {c["name"]: c for c in schema.get("columns", [])}
    allowed, keys = _allowed_values(schema), _key_columns(schema)
    profiles = []
    for i, name in enumerate(upload.columns):
        cells = [(line, row[i]) for line, row in zip(upload.lines, upload.rows)]
        values = [v for _, v in cells if not is_null(v)]
        shapes = Counter(value_shape(v) for _, v in cells)
        column = by_name.get(name)
        profile: dict[str, Any] = {
            "column": name,
            "target_type": column["data_type"] if column else None,
            "in_target_table": column is not None,
            "empty": shapes.pop("empty", 0),
            "distinct": len(set(values)),
            "shapes": dict(shapes.most_common()),
        }
        if shapes:
            usual = shapes.most_common(1)[0][0]
            profile["usual_shape"] = usual
            outliers = [{"row": line, "value": v, "shape": value_shape(v)}
                        for line, v in cells if not is_null(v) and value_shape(v) != usual]
            if outliers:
                profile["values_not_in_usual_shape"] = outliers[:MAX_OUTLIERS]
        ints = sorted({int(v) for v in values if _INTEGER.match(v)})
        if ints and profile.get("usual_shape") == "integer":
            profile["integer_range"] = {"min": ints[0], "max": ints[-1]}
            if ints[-1] - ints[0] <= MAX_SEQUENCE_SPAN:
                missing = sorted(set(range(ints[0], ints[-1] + 1)) - set(ints))
                profile["integer_range"]["missing_in_range"] = missing[:MAX_OUTLIERS * 2]
        if _categorical(profile["distinct"], len(values)) and name not in keys:
            profile["value_counts"] = dict(Counter(values).most_common())
        if name in allowed:
            upper = {a.upper(): a for a in allowed[name]}
            near = {v: upper[v.upper()] for v in set(values) if v not in allowed[name] and v.upper() in upper}
            if near:
                profile["case_only_mismatches"] = near  # uploaded value -> the allowed value it matches ignoring case
        profiles.append(profile)
    return profiles


def target_snapshot(conn: sqlite3.Connection, table: str, schema: dict[str, Any]) -> dict[str, Any]:
    """What the target table already holds: row count and, per column, a bounded summary."""
    t = f"main.{quote(table)}"
    snapshot: dict[str, Any] = {"row_count": conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], "columns": {}}
    keys = _key_columns(schema)
    for column in schema.get("columns", []):
        c = quote(column["name"])
        distinct = conn.execute(f"SELECT COUNT(DISTINCT {c}) FROM {t}").fetchone()[0]
        info: dict[str, Any] = {"distinct": distinct}
        if type_rule(column["data_type"]) in ("INTEGER", "REAL"):
            lo, hi = conn.execute(f"SELECT MIN({c}), MAX({c}) FROM {t}").fetchone()
            info.update(min=lo, max=hi)
        if _categorical(distinct, snapshot["row_count"]) and column["name"] not in keys:
            rows = conn.execute(f"SELECT {c}, COUNT(*) FROM {t} GROUP BY {c} ORDER BY COUNT(*) DESC").fetchall()
            info["value_counts"] = {str(v): n for v, n in rows}
        snapshot["columns"][column["name"]] = info
    return snapshot


def failing_row_numbers(validation_results: list[dict[str, Any]]) -> list[int]:
    """File row numbers named in the evidence of FAILED checks, in file order."""
    rows: set[int] = set()
    for result in validation_results:
        if result.get("status") != "FAILED":
            continue
        for line in result.get("evidence") or []:
            for group in _ROWS.findall(line):
                rows.update(int(n) for n in group.split(", "))
    return sorted(rows)


def failing_rows(upload: ParsedUpload, validation_results: list[dict[str, Any]]) -> dict[str, Any]:
    """The uploaded rows that failed checks, with every value (bounded)."""
    index = {line: i for i, line in enumerate(upload.lines)}
    numbers = [n for n in failing_row_numbers(validation_results) if n in index]
    return {
        "rows": [{"row": n, "values": dict(zip(upload.columns, upload.rows[index[n]]))}
                 for n in numbers[:MAX_FAILING_ROWS]],
        "rows_sent": min(len(numbers), MAX_FAILING_ROWS),
        "rows_failing_in_evidence": len(numbers),
        "rows_in_file": upload.row_count,
    }


def run_history(record: Any, runs: list[Any]) -> list[dict[str, Any]]:
    """The earlier attempts this run retries (its parent, the parent's parent, ...), newest first. Unrelated runs are
    never included: the investigation stays scoped to this run and its own retry chain."""
    by_id = {r.run_id: r for r in runs}
    chain, parent_id = [], record.parent_run_id
    while parent_id and parent_id in by_id and len(chain) < MAX_HISTORY:
        parent = by_id[parent_id]
        chain.append({
            "run_id": parent.run_id,
            "file_name": parent.file_name,
            "status": parent.status,
            "created_at": parent.created_at,
            "failed_checks": [v["name"] for v in parent.validation_results if v["status"] == "FAILED"],
            "failed_evidence": [line for v in parent.validation_results if v["status"] == "FAILED"
                                for line in v.get("evidence") or []][:MAX_FAILING_ROWS],
        })
        parent_id = parent.parent_run_id
    return chain


# --- row fixes ---------------------------------------------------------------------------------

def _satisfies(value: str | None, column: dict[str, Any] | None, allowed: dict[str, list[str]]) -> bool:
    """Whether a suggested value passes the column's own rules (type, NOT NULL, CHECK). Keys are not checked."""
    if column is None or value is None:
        return False
    if is_null(value):
        return column["nullable"] and not column["primary_key"]
    if not conforms(value, type_rule(column["data_type"])):
        return False
    return value in allowed.get(column["name"], [value])


def verify_row_fixes(raw: list[dict[str, Any]], upload: ParsedUpload,
                     schema: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Check each AI-suggested fix against the actual file.

    A fix naming a row or column that doesn't exist is dropped. The current value is always taken from the file,
    and `satisfies_constraints` says whether the suggested value passes the column's type, NOT NULL and CHECK rules
    (duplicate keys are re-checked only when the corrected file is validated). Returns (fixes, warnings)."""
    index = {line: i for i, line in enumerate(upload.lines)}
    position = {name: i for i, name in enumerate(upload.columns)}
    by_name = {c["name"]: c for c in schema.get("columns", [])}
    allowed = _allowed_values(schema)
    fixes, warnings = [], []
    for i, f in enumerate(raw):
        row, column = f.get("row"), f.get("column")
        if row not in index:
            warnings.append(f"row_fixes[{i}] names row {row!r}, which is not a data row of the file; it was dropped")
            continue
        if f["action"] != "DELETE_ROW" and column not in position:
            warnings.append(f"row_fixes[{i}] names column {column!r}, which is not in the file; it was dropped")
            continue
        actual = upload.rows[index[row]][position[column]] if column in position else None
        if f.get("current_value") is not None and actual is not None and str(f["current_value"]) != actual:
            warnings.append(f"row_fixes[{i}] quoted {f['current_value']!r} for row {row} `{column}`, but the file has "
                            f"{actual!r}; the file's value is shown")
        suggested = f.get("suggested_value")
        if f["action"] == "REPLACE" and suggested == actual:
            warnings.append(f"row_fixes[{i}] suggests the value row {row} `{column}` already has; it was dropped")
            continue
        fixes.append({
            **f,
            "column": column if column in position else None,
            "current_value": actual,
            "satisfies_constraints": (f["action"] == "DELETE_ROW"
                                      or (f["action"] == "REPLACE" and _satisfies(suggested, by_name.get(column), allowed))),
        })
    return fixes, warnings


def applicable_fixes(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The fixes the suggested CSV applies: REPLACE and DELETE_ROW. NEEDS_DECISION is left to the user."""
    return [f for f in fixes if f.get("action") in ("REPLACE", "DELETE_ROW")]


def apply_row_fixes(upload: ParsedUpload, fixes: list[dict[str, Any]]) -> str:
    """The uploaded CSV with the applicable fixes applied, as CSV text (header and row order kept)."""
    position = {name: i for i, name in enumerate(upload.columns)}
    replace = {(f["row"], f["column"]): f["suggested_value"] for f in applicable_fixes(fixes)
               if f["action"] == "REPLACE" and f.get("column") in position}
    delete = {f["row"] for f in applicable_fixes(fixes) if f["action"] == "DELETE_ROW"}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(upload.columns)
    for line, row in zip(upload.lines, upload.rows):
        if line in delete:
            continue
        writer.writerow([replace.get((line, name), value) for name, value in zip(upload.columns, row)])
    return out.getvalue()
