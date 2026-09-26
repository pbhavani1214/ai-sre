"""Discover a target table's schema and constraints from SQLite itself.

Columns and NOT NULL come from PRAGMA table_info, the primary key from its pk flag, UNIQUE from
PRAGMA index_list / index_info, and CHECK constraints from the CREATE TABLE statement stored in
sqlite_master. Only the `column IN ('a', 'b', ...)` form of CHECK is interpreted (allowed
values); any other CHECK is reported with its expression and no allowed values.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any


class TableNotFound(LookupError):
    pass


def quote(name: str) -> str:
    """Quote an SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


_IN_LIST = re.compile(r'^\s*("(?:[^"]|"")+"|\w+)\s+IN\s*\((.*)\)\s*$', re.IGNORECASE | re.DOTALL)
_LITERAL = re.compile(r"\s*'((?:[^']|'')*)'\s*(?:,|$)")
_CHECK = re.compile(r"\bCHECK\s*\(", re.IGNORECASE)


def _check_bodies(ddl: str) -> list[str]:
    """The expression inside each CHECK (...) of a CREATE TABLE statement, skipping string literals."""
    bodies, i, n = [], 0, len(ddl)
    while i < n:
        if ddl[i] in "'\"":  # skip a quoted string or identifier
            j = i + 1
            while j < n and not (ddl[j] == ddl[i] and (j + 1 == n or ddl[j + 1] != ddl[i])):
                j += 2 if ddl[j] == ddl[i] else 1
            i = j + 1
            continue
        m = _CHECK.match(ddl, i)
        if m and (i == 0 or not (ddl[i - 1].isalnum() or ddl[i - 1] == "_")):
            depth, j, quote_ch = 1, m.end(), None
            while j < n and depth:
                ch = ddl[j]
                if quote_ch:
                    quote_ch = None if ch == quote_ch else quote_ch
                elif ch in "'\"":
                    quote_ch = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                j += 1
            bodies.append(ddl[m.end() : j - 1].strip())
            i = j
            continue
        i += 1
    return bodies


def _allowed_values(expression: str) -> tuple[str, list[str]] | None:
    """(column, values) for `column IN ('a', 'b')`, else None."""
    m = _IN_LIST.match(expression)
    if not m:
        return None
    values, rest = [], m.group(2).strip()
    while rest:
        lit = _LITERAL.match(rest)
        if not lit:
            return None
        values.append(lit.group(1).replace("''", "'"))
        rest = rest[lit.end():].strip()
    return m.group(1).strip('"').replace('""', '"'), values


def discover_schema(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    """Columns and constraints of `table`, in the shape of CONTRACT.md's target schema."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    if row is None:
        raise TableNotFound(table)
    ddl = row[0]

    info = conn.execute(f"PRAGMA table_info({quote(table)})").fetchall()  # cid, name, type, notnull, dflt, pk
    primary_key = [r[1] for r in sorted((r for r in info if r[5]), key=lambda r: r[5])]
    unique_keys = []
    for _, index, unique, origin, partial in conn.execute(f"PRAGMA index_list({quote(table)})").fetchall():
        if unique and origin != "pk" and not partial:
            cols = [c[2] for c in conn.execute(f"PRAGMA index_info({quote(index)})").fetchall()]
            if cols and cols not in unique_keys:
                unique_keys.append(cols)
    single_unique = {k[0] for k in unique_keys if len(k) == 1}
    # PRAGMA reports notnull=0 for INTEGER PRIMARY KEY (it's the rowid), but a primary key is never null here.
    explicit_not_null = [r[1] for r in info if r[3]]

    columns = [
        {
            "name": r[1],
            "data_type": r[2],
            "nullable": not (r[3] or r[1] in primary_key),
            "primary_key": r[1] in primary_key,
            "unique": r[1] in single_unique,
        }
        for r in info
    ]

    constraints: list[dict[str, Any]] = []
    if primary_key:
        constraints.append({"type": "PRIMARY_KEY", "columns": primary_key,
                            "description": f"{', '.join(primary_key)} must be unique and non-null"})
    for key in unique_keys:
        constraints.append({"type": "UNIQUE", "columns": key, "description": f"{', '.join(key)} must be unique"})
    if explicit_not_null:
        constraints.append({"type": "NOT_NULL", "columns": explicit_not_null,
                            "description": "Required fields cannot be null"})
    for expression in _check_bodies(ddl):
        parsed = _allowed_values(expression)
        if parsed:
            column, values = parsed
            constraints.append({"type": "CHECK", "columns": [column], "allowed_values": values,
                                "description": f"{column} must contain an allowed value"})
        else:
            constraints.append({"type": "CHECK", "columns": [], "description": f"CHECK ({expression})"})
    return {"columns": columns, "constraints": constraints}
