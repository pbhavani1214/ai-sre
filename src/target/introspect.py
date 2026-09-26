"""Read a target table's definition back from SQLite: columns, keys, CHECK constraints and DDL.

Everything the upload pipeline validates comes from here, so any table works, not just the demo.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

SAMPLE_ROWS = 3


class TargetNotFound(LookupError):
    pass


def quote(name: str) -> str:
    """Quote an SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def affinity(declared_type: str) -> str:
    """SQLite column affinity from a declared type (https://sqlite.org/datatype3.html, 3.1)."""
    t = (declared_type or "").upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if not t or "BLOB" in t:
        return "BLOB"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r[0] for r in rows]


def row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM main.{quote(table)}").fetchone()[0]


def _skip_quoted(sql: str, i: int) -> int:
    """Index just past the quoted token or comment starting at sql[i], or i if there is none."""
    ch = sql[i]
    if ch in "'\"`[":
        end_ch = "]" if ch == "[" else ch
        j = i + 1
        while j < len(sql):
            if sql[j] == end_ch:
                if end_ch != "]" and j + 1 < len(sql) and sql[j + 1] == end_ch:  # doubled quote
                    j += 2
                    continue
                return j + 1
            j += 1
        return len(sql)
    if sql.startswith("--", i):
        j = sql.find("\n", i)
        return len(sql) if j == -1 else j + 1
    if sql.startswith("/*", i):
        j = sql.find("*/", i + 2)
        return len(sql) if j == -1 else j + 2
    return i


def check_constraints(ddl: str) -> list[dict[str, str]]:
    """Every CHECK (...) in a CREATE TABLE statement, with its CONSTRAINT name if it has one."""
    found, i = [], 0
    while i < len(ddl):
        j = _skip_quoted(ddl, i)
        if j != i:
            i = j
            continue
        if (ddl[i : i + 5].upper() == "CHECK" and (i == 0 or not (ddl[i - 1].isalnum() or ddl[i - 1] == "_"))
                and not (i + 5 < len(ddl) and (ddl[i + 5].isalnum() or ddl[i + 5] == "_"))):
            k = i + 5
            while k < len(ddl) and ddl[k].isspace():
                k += 1
            if k < len(ddl) and ddl[k] == "(":
                depth, m = 0, k
                while m < len(ddl):
                    n = _skip_quoted(ddl, m)
                    if n != m:
                        m = n
                        continue
                    if ddl[m] == "(":
                        depth += 1
                    elif ddl[m] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    m += 1
                named = re.search(r"CONSTRAINT\s+(\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|\w+)\s*$", ddl[:i], re.IGNORECASE)
                name = named.group(1).strip('"`[]') if named else f"check_{len(found) + 1}"
                found.append({"name": name, "expression": ddl[k + 1 : m].strip()})
                i = m + 1
                continue
        i += 1
    return found


def describe_table(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    """The table's definition as it exists in the database right now."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ? AND name NOT LIKE 'sqlite_%'",
        (table,)).fetchone()
    if row is None:
        raise TargetNotFound(table)
    ddl = row[0]

    info = conn.execute(f"PRAGMA table_info({quote(table)})").fetchall()  # cid, name, type, notnull, dflt, pk
    pk = [r[1] for r in sorted((r for r in info if r[5]), key=lambda r: r[5])]
    unique_keys = [pk] if pk else []
    for idx in conn.execute(f"PRAGMA index_list({quote(table)})").fetchall():  # seq, name, unique, origin, partial
        if idx[2] and not idx[4]:
            cols = [c[2] for c in conn.execute(f"PRAGMA index_info({quote(idx[1])})").fetchall()]
            if cols and cols not in unique_keys:
                unique_keys.append(cols)
    single_unique = {k[0] for k in unique_keys if len(k) == 1}

    columns = [
        {
            "name": r[1],
            "type": r[2],
            "affinity": affinity(r[2]),
            "not_null": bool(r[3]),
            "default": r[4],
            "primary_key": r[1] in pk,
            "unique": r[1] in single_unique,
        }
        for r in info
    ]
    cur = conn.execute(f"SELECT * FROM main.{quote(table)} LIMIT {SAMPLE_ROWS}")
    names = [d[0] for d in cur.description]
    return {
        "name": table,
        "ddl": ddl,
        "row_count": row_count(conn, table),
        "columns": columns,
        "primary_key": pk,
        "unique_keys": unique_keys,
        "check_constraints": check_constraints(ddl),
        "sample_rows": [dict(zip(names, r)) for r in cur.fetchall()],
    }
