"""Read an uploaded CSV file: size and row limits, UTF-8 decoding, header and row-shape checks.

Problems here mean the file can't be read at all, so no run is created and the API returns an
error. Problems with the data itself are the pipeline's job (pipeline.py) and produce a failed run.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import BinaryIO

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_ROWS = 50_000
CHUNK = 64 * 1024


class UploadError(Exception):
    def __init__(self, status_code: int, code: str, message: str, field: str | None = "file"):
        super().__init__(message)
        self.status_code, self.code, self.message, self.field = status_code, code, message, field

    def detail(self) -> dict:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass
class ParsedUpload:
    columns: list[str]
    rows: list[dict[str, str | None]]  # every column present; empty cells are None
    lines: list[int] = field(default_factory=list)  # file line number of each row (header is line 1)


def read_limited(stream: BinaryIO, limit: int = None) -> bytes:
    """Read in chunks and stop as soon as the file is over the limit."""
    limit = MAX_UPLOAD_BYTES if limit is None else limit
    buf, size = io.BytesIO(), 0
    while chunk := stream.read(CHUNK):
        size += len(chunk)
        if size > limit:
            raise UploadError(413, "file_too_large", f"The file is over the {limit / 1024 / 1024:g} MB limit.")
        buf.write(chunk)
    return buf.getvalue()


def parse_csv(data: bytes) -> ParsedUpload:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise UploadError(422, "invalid_encoding",
                          f"The file isn't valid UTF-8 (byte {e.start}). Save it as UTF-8 CSV and upload it again.")
    if not text.strip():
        raise UploadError(422, "invalid_csv", "The file is empty.")

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
        columns = [h.strip() for h in header]
        for i, name in enumerate(columns, start=1):
            if not name:
                raise UploadError(422, "invalid_header", f"Column {i} in the header has no name.")
        dupes = sorted({c for c in columns if columns.count(c) > 1})
        if dupes:
            raise UploadError(422, "invalid_header",
                              f"The header has more than one column named {', '.join(repr(d) for d in dupes)}. "
                              "Column names must be unique.")

        rows, lines = [], []
        for values in reader:
            if not values:
                continue  # blank line
            if len(values) != len(columns):
                raise UploadError(422, "invalid_csv",
                                  f"Line {reader.line_num} has {len(values)} fields, but the header has {len(columns)}.")
            if len(rows) == MAX_UPLOAD_ROWS:
                raise UploadError(422, "too_many_rows", f"The file has more than {MAX_UPLOAD_ROWS:,} data rows.")
            rows.append({c: (v if v != "" else None) for c, v in zip(columns, values)})
            lines.append(reader.line_num)
    except csv.Error as e:
        raise UploadError(422, "invalid_csv", f"The file can't be read as CSV (line {reader.line_num}): {e}.")

    if not rows:
        raise UploadError(422, "invalid_csv", "The file has a header but no data rows.")
    return ParsedUpload(columns, rows, lines)
