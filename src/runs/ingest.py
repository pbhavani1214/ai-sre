"""Parse and validate uploaded run files (see docs/implementation/CONTRACT.md, "Phase 1: uploads").

Every failure raises UploadError, whose message is shown to the user as-is.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from typing import Any, BinaryIO, Protocol

import pandas as pd

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 50_000
MAX_RUN_LOG_BYTES = 1024 * 1024
CHUNK_BYTES = 64 * 1024


class UploadError(Exception):
    def __init__(self, status_code: int, code: str, message: str, field: str | None):
        super().__init__(message)
        self.status_code, self.code, self.message, self.field = status_code, code, message, field

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "field": self.field}


class _Upload(Protocol):
    file: BinaryIO


def _size(limit: int) -> str:
    mb = 1024 * 1024
    return f"{limit // mb} MB" if limit % mb == 0 else f"{limit:,} bytes"


def read_limited(upload: _Upload, limit: int, field: str) -> bytes:
    """Read an upload in chunks, failing with 413 as soon as it passes `limit` bytes."""
    buf = bytearray()
    while chunk := upload.file.read(CHUNK_BYTES):
        buf += chunk
        if len(buf) > limit:
            raise UploadError(413, "file_too_large", f"{field} is larger than the {_size(limit)} limit.", field)
    return bytes(buf)


def _invalid_csv(field: str, message: str) -> UploadError:
    return UploadError(422, "invalid_csv", f"{field} {message}", field)


def parse_csv(data: bytes, field: str) -> pd.DataFrame:
    """Decode and parse one uploaded CSV. All values are strings; empty cells are null."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UploadError(422, "invalid_encoding",
                          f"{field} is not UTF-8 encoded. Save it as UTF-8 CSV and upload it again.", field)
    if not text.strip():
        raise _invalid_csv(field, "is empty.")

    # Structure check with the csv module first: pandas hides duplicate headers (renames them
    # to "name.1"), names empty ones "Unnamed: N", and silently turns the first column into the
    # index when every data row has one field too many.
    try:
        reader = csv.reader(io.StringIO(text, newline=""))
        header = [h.strip() for h in next(reader)]
        for i, name in enumerate(header, start=1):
            if not name:
                raise UploadError(422, "invalid_header",
                                  f"{field} has an empty column name (column {i}). Every column needs a name.", field)
        for name, count in Counter(header).items():
            if count > 1:
                raise UploadError(422, "invalid_header",
                                  f"{field} has {count} columns named '{name}'. Column names must be unique.", field)
        rows = 0
        for row in reader:
            if not row:  # blank line; pandas skips these too
                continue
            rows += 1
            if len(row) > len(header):
                raise _invalid_csv(field, f"could not be read: line {reader.line_num} has {len(row)} fields, "
                                          f"but the header has {len(header)}.")
    except csv.Error as e:
        raise _invalid_csv(field, f"could not be read as CSV ({e}).")

    if rows == 0:
        raise _invalid_csv(field, "has a header row but no data rows.")
    if rows > MAX_CSV_ROWS:
        raise UploadError(422, "too_many_rows",
                          f"{field} has {rows:,} data rows; the limit is {MAX_CSV_ROWS:,}.", field)

    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=[""])
    except pd.errors.EmptyDataError:
        raise _invalid_csv(field, "is empty.")
    except pd.errors.ParserError as e:
        reason = str(e).split("C error: ")[-1].strip().rstrip(".")
        raise _invalid_csv(field, f"could not be read as CSV ({reason}).")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not allowed")


def parse_pipeline_run(data: bytes | None) -> dict[str, Any] | None:
    """Validate the optional run log. Returns None when no file was provided."""
    field = "pipeline_run_file"
    if not data:
        return None

    def bad(message: str) -> UploadError:
        return UploadError(422, "invalid_pipeline_run", f"{field} {message}", field)

    try:
        run = json.loads(data.decode("utf-8-sig"), parse_constant=_reject_constant)
    except UnicodeDecodeError:
        raise bad("is not UTF-8 encoded.")
    except json.JSONDecodeError as e:
        raise bad(f"is not valid JSON ({e.msg} at line {e.lineno}, column {e.colno}).")
    except ValueError as e:  # NaN / Infinity
        raise bad(f"is not valid JSON ({e}).")

    if not isinstance(run, dict):
        raise bad(f"must contain a JSON object, not {_json_type(run)}.")
    steps = run.get("steps")
    if steps is not None:
        if not isinstance(steps, list):
            raise bad(f"has 'steps' as {_json_type(steps)}; it must be a list.")
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or not isinstance(step.get("name"), str):
                raise bad(f"has an invalid steps[{i}]: each step must be an object with a text 'name'.")
    logs = run.get("logs")
    if logs is not None:
        if not isinstance(logs, list):
            raise bad(f"has 'logs' as {_json_type(logs)}; it must be a list of text lines.")
        for i, line in enumerate(logs):
            if not isinstance(line, str):
                raise bad(f"has an invalid logs[{i}] ({_json_type(line)}); every log line must be text.")
    return run


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "true/false"
    return {dict: "an object", list: "a list", str: "text", int: "a number", float: "a number",
            type(None): "null"}.get(type(value), type(value).__name__)
