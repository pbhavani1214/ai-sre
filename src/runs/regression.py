"""A reusable data check for a target table, generated from its discovered schema (not by the AI).

The generated pytest module has no dependencies beyond the standard library. It holds:

- `problems(header, rows)`: the table's rules (required columns, types, NOT NULL, PRIMARY KEY and UNIQUE
  duplicates within the file, CHECK allowed values), the same rules the backend validates before a load;
- a test that the rows which failed in this run are still caught, and which checks catch them;
- a test for any CSV you point it at with the CSV_PATH environment variable (skipped when it isn't set).

Values already stored in the table can't be seen from a standalone test, so those conflicts are only caught by
the backend. This system never runs the generated file.
"""

from __future__ import annotations

import re
from typing import Any

from src.runs.insights import failing_row_numbers
from src.runs.ingest import ParsedUpload
from src.runs.validation import type_rule

RULES = '''
_INTEGER = re.compile(r"^[+-]?\\d+$")
_REAL = re.compile(r"^[+-]?(\\d+(\\.\\d*)?|\\.\\d+)([eE][+-]?\\d+)?$")
_PATTERN = {"INTEGER": _INTEGER, "REAL": _REAL}


def _key(values, columns):
    return tuple(int(v) if TYPES.get(c) == "INTEGER" and _INTEGER.match(v)
                 else float(v) if TYPES.get(c) == "REAL" and _REAL.match(v) else v
                 for v, c in zip(values, columns))


def problems(header, rows):
    """[(check name, message)] for a CSV header and its data rows (lists of strings)."""
    found = []
    pos = {name: i for i, name in enumerate(header)}
    for name in REQUIRED:
        if name not in pos:
            found.append(("required_columns", f"required column `{name}` is missing"))
    for n, row in enumerate(rows, start=2):
        for name, i in pos.items():
            value = row[i]
            if value == "":
                if name in NOT_NULL:
                    found.append(("not_null", f"`{name}` is empty at row {n}"))
                continue
            pattern = _PATTERN.get(TYPES.get(name))
            if pattern and not pattern.match(value):
                found.append(("data_type_compatibility", f"{name}={value!r} is not a valid {TYPES[name]} at row {n}"))
            if name in ALLOWED and value not in ALLOWED[name]:
                found.append(("check_constraints", f"{name}={value!r} is not an allowed value at row {n}"))
    for check, keys in (("primary_key_uniqueness", [PRIMARY_KEY] if PRIMARY_KEY else []), ("unique_constraints", UNIQUE)):
        for columns in keys:
            if not all(c in pos for c in columns):
                continue
            seen = {}
            for n, row in enumerate(rows, start=2):
                values = [row[pos[c]] for c in columns]
                if "" in values:
                    continue
                seen.setdefault(_key(values, columns), []).append(n)
            for k, at in seen.items():
                if len(at) > 1:
                    found.append((check, f"{columns}={k} appears {len(at)} times (rows {at})"))
    return found
'''


def _py(value: Any) -> str:
    return repr(value)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "table"


def generate(schema: dict[str, Any], upload: ParsedUpload, validation_results: list[dict[str, Any]],
             table: str, database: str, run_id: str) -> tuple[str, str]:
    """(test name, pytest source) for the table, seeded with this run's failing rows."""
    columns = schema.get("columns", [])
    constraints = schema.get("constraints", [])
    with_default = set(schema.get("columns_with_default", []))
    types = {c["name"]: rule for c in columns if (rule := type_rule(c["data_type"]))}
    required = [c["name"] for c in columns if c["primary_key"] or (not c["nullable"] and c["name"] not in with_default)]
    not_null = [c["name"] for c in columns if not c["nullable"]]
    pk = next((c["columns"] for c in constraints if c["type"] == "PRIMARY_KEY"), [])
    unique = [c["columns"] for c in constraints if c["type"] == "UNIQUE"]
    allowed = {c["columns"][0]: c["allowed_values"] for c in constraints
               if c["type"] == "CHECK" and c.get("allowed_values") is not None and len(c["columns"]) == 1}

    index = {line: i for i, line in enumerate(upload.lines)}
    bad_rows = [upload.rows[index[n]] for n in failing_row_numbers(validation_results) if n in index]
    name = f"test_{_slug(table)}_data"
    head = f'''"""Data check for table `{table}` in {database}, generated from its schema by AI SRE for run {run_id}.

Run it with pytest. To check a CSV before uploading it:
    CSV_PATH=path/to/file.csv pytest {name}.py
Values that already exist in the table are only caught by the backend, not by this standalone check.
"""
import csv
import os
import re

import pytest

TYPES = {_py(types)}
REQUIRED = {_py(required)}
NOT_NULL = {_py(not_null)}
PRIMARY_KEY = {_py(pk)}
UNIQUE = {_py(unique)}
ALLOWED = {_py(allowed)}
'''
    namespace: dict[str, Any] = {"re": re, "TYPES": types, "REQUIRED": required, "NOT_NULL": not_null,
                                 "PRIMARY_KEY": pk, "UNIQUE": unique, "ALLOWED": allowed}
    exec(RULES, namespace)  # our own fixed source: computes which checks the embedded rows trigger
    caught = sorted({check for check, _ in namespace["problems"](upload.columns, bad_rows)}) if bad_rows else []
    tests = f'''

# The rows of {run_id} that failed validation, as uploaded.
FAILED_HEADER = {_py(upload.columns)}
FAILED_ROWS = [
{"".join(f"    {_py(r)},{chr(10)}" for r in bad_rows)}]


def test_failed_rows_are_still_caught():
    found = sorted({{check for check, _ in problems(FAILED_HEADER, FAILED_ROWS)}})
    assert found == {_py(caught)}


@pytest.mark.skipif(not os.getenv("CSV_PATH"), reason="set CSV_PATH to check a CSV file")
def test_csv_file_passes():
    with open(os.environ["CSV_PATH"], newline="", encoding="utf-8-sig") as f:
        header, *rows = [r for r in csv.reader(f) if r]
    assert problems(header, rows) == []
'''
    return name, head + RULES + tests
