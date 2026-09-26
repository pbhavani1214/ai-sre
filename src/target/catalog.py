"""The databases a user can choose from, and the tables in each (CONTRACT.md "Databases").

Every SQLite file (*.db, *.sqlite, *.sqlite3) in the database folder is a database; the default database is always
included, even when it lives elsewhere. A database_id is the file name without its extension. Request values are
only ever matched against this list, never joined into a path, so a database_id can't reach other files.

Tables are discovered from sqlite_master: every table in a database is a possible target. The target_id is the
table name.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from src.target.database import initialize_demo_databases

SUFFIXES = (".db", ".sqlite", ".sqlite3")
_SQLITE_HEADER = b"SQLite format 3\x00"

# Friendlier names for the demo databases and tables; anything else is derived from its name.
DATABASE_NAMES = {"crm": "CRM", "sales": "Sales"}
TABLE_DESCRIPTIONS = {
    "customer": "Customer master data",
    "orders": "Customer orders",
    "products": "Product catalog",
}


def humanize(name: str) -> str:
    """"order_items" -> "Order items"."""
    text = re.sub(r"[_\-]+", " ", name).strip()
    return text[:1].upper() + text[1:]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", text.lower()).strip("_") or "database"


def _is_sqlite(path: Path) -> bool:
    """An empty file is a valid (empty) SQLite database; anything else must carry the SQLite header."""
    try:
        if path.stat().st_size == 0:
            return True
        with path.open("rb") as f:
            return f.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER
    except OSError:
        return False


def list_tables(path: Path | str) -> list[str]:
    """User tables in a SQLite database, by name (SQLite's internal sqlite_* tables excluded)."""
    with closing(sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)) as conn:
        return [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' "
            "ORDER BY name")]


@dataclass(frozen=True)
class Database:
    database_id: str
    file_name: str
    path: Path
    is_default: bool

    @property
    def display_name(self) -> str:
        return DATABASE_NAMES.get(self.database_id, humanize(self.database_id))

    def to_dict(self) -> dict:
        return {
            "database_id": self.database_id, "display_name": self.display_name, "file_name": self.file_name,
            "database_type": "sqlite", "table_count": len(list_tables(self.path)), "is_default": self.is_default,
        }


def target_summary(database: Database, table: str) -> dict:
    """The contract's TargetSummary for one table of a database."""
    return {"target_id": table, "table_name": table, "display_name": humanize(table),
            "description": TABLE_DESCRIPTIONS.get(table), "database_type": "sqlite",
            "database_id": database.database_id}


class DatabaseCatalog:
    """The databases in one folder plus the default database. Nothing is read or created until it is used, so
    endpoints that only need the default database never touch the folder."""

    def __init__(self, directory: Path | str, default_path: Path | str, seed_demo: bool = True):
        self.directory = Path(directory)
        self.default_path = Path(default_path)
        self.seed_demo = seed_demo

    def default(self) -> Database:
        return Database(_slug(self.default_path.stem), self.default_path.name, self.default_path, True)

    def databases(self) -> list[Database]:
        """The default database first, then the folder's other SQLite files by name."""
        if self.seed_demo:
            initialize_demo_databases(self.directory)
        default = self.default()
        result, seen = [default], {default.database_id}
        default_resolved = self.default_path.resolve()
        files = sorted(p for p in self.directory.iterdir()
                       if p.is_file() and p.suffix.lower() in SUFFIXES) if self.directory.is_dir() else []
        for path in files:
            if path.resolve() == default_resolved or not _is_sqlite(path):
                continue
            database_id = _slug(path.stem)
            if database_id in seen:  # e.g. crm.db and crm.sqlite: keep them apart by the full file name
                database_id = _slug(path.name)
            if database_id in seen:
                continue
            seen.add(database_id)
            result.append(Database(database_id, path.name, path, False))
        return result

    def resolve(self, database_id: str | None) -> Database | None:
        """The named database, or the default one when no database_id is given. None when it doesn't exist."""
        default = self.default()
        if database_id is None or database_id == "" or database_id == default.database_id:
            return default  # no need to scan (or seed) the database folder
        return next((d for d in self.databases() if d.database_id == database_id), None)
