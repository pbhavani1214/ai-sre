"""Upload envelope checks for POST /api/runs: file type, size, UTF-8, header and CSV structure.

A file that fails here is rejected with a structured error and no run is created. Checking
the data against the target table is the validation engine's job, not this module's.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import BinaryIO

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB (CONTRACT.md, "File requirements")
CHUNK_BYTES = 64 * 1024


class UploadError(Exception):
    def __init__(self, status_code: int, code: str, message: str, field: str | None = "file"):
        super().__init__(message)
        self.status_code, self.code, self.message, self.field = status_code, code, message, field

    def detail(self) -> dict:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass
class ParsedUpload:
    """The uploaded CSV, kept in memory for later milestones. Values are the raw cell strings."""

    columns: list[str]  # header names exactly as uploaded, in file order
    rows: list[list[str]]  # data rows in file order, one value per column
    lines: list[int]  # file line number of each row (the header is line 1)

    @property
    def row_count(self) -> int:
        return len(self.rows)


def check_file_type(file_name: str | None) -> None:
    if not file_name or not file_name.lower().endswith(".csv"):
        raise UploadError(422, "unsupported_file_type",
                          f"'{file_name or ''}' is not a CSV file. Upload a file with a .csv extension.")


def read_limited(stream: BinaryIO, limit: int | None = None) -> bytes:
    """Read the upload in chunks and stop as soon as it goes over the limit."""
    limit = MAX_UPLOAD_BYTES if limit is None else limit
    buf, size = io.BytesIO(), 0
    while chunk := stream.read(CHUNK_BYTES):
        size += len(chunk)
        if size > limit:
            raise UploadError(413, "file_too_large", f"The file is larger than the {limit / 1024 / 1024:g} MB limit.")
        buf.write(chunk)
    return buf.getvalue()


def parse_csv(data: bytes) -> ParsedUpload:
    try:
        text = data.decode("utf-8-sig")  # a UTF-8 byte order mark is allowed
    except UnicodeDecodeError as e:
        raise UploadError(422, "invalid_file",
                          f"The file is not valid UTF-8 (byte {e.start}). Save it as UTF-8 CSV and upload it again.")
    if not text.strip():
        raise UploadError(422, "empty_file", "The file is empty.")

    if "\x00" in text:
        raise UploadError(422, "malformed_csv", "The file contains NUL bytes, so it isn't a text CSV file.")

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)  # strict: bad quoting is an error
    try:
        header = next(reader)
        if not header or any(not name.strip() for name in header):
            raise UploadError(422, "missing_header",
                              "The first line must be a header row that names every column.")
        dupes = sorted({name for name in header if header.count(name) > 1})
        if dupes:
            raise UploadError(422, "malformed_csv",
                              f"The header has more than one column named {', '.join(repr(d) for d in dupes)}.")
        rows, lines = [], []
        for values in reader:
            if not values:
                continue  # blank line
            if len(values) != len(header):
                raise UploadError(422, "malformed_csv",
                                  f"Line {reader.line_num} has {len(values)} fields, but the header has {len(header)}.")
            rows.append(values)
            lines.append(reader.line_num)
    except csv.Error as e:
        raise UploadError(422, "malformed_csv", f"The file can't be read as CSV (line {reader.line_num}): {e}.")

    if not rows:
        raise UploadError(422, "empty_file", "The file has a header row but no data rows.")
    return ParsedUpload(header, rows, lines)
