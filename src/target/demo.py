"""The demo target database: an existing SQLite warehouse with a `customers` table.

The table's DDL is the only definition of what valid data looks like. The upload pipeline
reads it back from SQLite (see introspect.py) and derives every validation from it, so
nothing here is known to the pipeline or the AI except through the database itself.

    python -m src.target.demo     # (re)create the demo database at TARGET_DB_PATH
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DATA_DIR, target_db_path

DEMO_UPLOADS_DIR = DATA_DIR / "demo_uploads"
DEMO_UPLOAD_FILES = ("customers_upload_bad.csv", "customers_upload_fixed.csv")

CUSTOMERS_DDL = """CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    country     TEXT NOT NULL CONSTRAINT country_iso2 CHECK (length(country) = 2 AND country = upper(country)),
    signup_date TEXT NOT NULL CONSTRAINT signup_date_iso CHECK (date(signup_date) IS signup_date),
    status      TEXT NOT NULL CONSTRAINT status_allowed CHECK (status IN ('active', 'inactive', 'churned')),
    CONSTRAINT email_format CHECK (email LIKE '%_@_%._%')
)"""

# Customers already in the warehouse before any upload.
SEED_CUSTOMERS = [
    (1001, "Alice Carter", "alice.carter@example.com", "US", "2024-01-05", "active"),
    (1002, "Bob Singh", "bob.singh@example.com", "IN", "2024-01-09", "active"),
    (1003, "Chloe Martin", "chloe.martin@example.com", "GB", "2024-01-12", "active"),
    (1004, "Daniel Tan", "daniel.tan@example.com", "SG", "2024-01-15", "active"),
    (1005, "Eva Schmidt", "eva.schmidt@example.com", "DE", "2024-01-20", "inactive"),
    (1006, "Farah Khan", "farah.khan@example.com", "IN", "2024-02-02", "active"),
    (1007, "George Brown", "george.brown@example.com", "US", "2024-02-07", "active"),
    (1008, "Hannah Lee", "hannah.lee@example.com", "AU", "2024-02-11", "churned"),
    (1009, "Ivan Petrov", "ivan.petrov@example.com", "DE", "2024-02-18", "active"),
    (1010, "Julia Rossi", "julia.rossi@example.com", "GB", "2024-02-25", "active"),
]


def reset_demo_database(path: Path | str | None = None) -> Path:
    """Drop and recreate the demo database with only the seed customers."""
    path = Path(path or target_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE IF EXISTS customers")
        conn.execute(CUSTOMERS_DDL)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", SEED_CUSTOMERS)
    conn.close()
    return path


def ensure_demo_database(path: Path | str | None = None) -> Path:
    """Create the demo database if the file doesn't exist yet. Never touches an existing file."""
    path = Path(path or target_db_path())
    return path if path.exists() else reset_demo_database(path)


if __name__ == "__main__":
    print(f"Demo target database written to {reset_demo_database()}")
