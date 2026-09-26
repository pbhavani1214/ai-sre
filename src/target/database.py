"""The SQLite target database: the existing tables that uploaded data is loaded into.

The table DDL below is the only place the demo schema is written down. Everything else
(the API, and later the validation engine) reads it back from SQLite (see discovery.py).

Initialization is idempotent: a missing table is created and seeded, an existing one is left
untouched, so data survives restarts. To start over:

    python -m src.target.database --reset
"""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from src.config import target_db_path

CUSTOMER_DDL = """CREATE TABLE customer (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    country TEXT,
    signup_date TEXT,
    status TEXT CHECK(status IN ('ACTIVE', 'INACTIVE', 'CHURNED'))
)"""

# Customers already in the target before any upload.
CUSTOMER_SEED = [
    (1001, "Alice Carter", "alice.carter@example.com", "US", "2024-01-05", "ACTIVE"),
    (1002, "Bob Singh", "bob.singh@example.com", "IN", "2024-01-09", "ACTIVE"),
    (1003, "Chloe Martin", "chloe.martin@example.com", "GB", "2024-01-12", "ACTIVE"),
    (1004, "Daniel Tan", "daniel.tan@example.com", "SG", "2024-01-15", "ACTIVE"),
    (1005, "Eva Schmidt", "eva.schmidt@example.com", "DE", "2024-01-20", "INACTIVE"),
    (1006, "Farah Khan", "farah.khan@example.com", "IN", "2024-02-02", "ACTIVE"),
    (1007, "George Brown", "george.brown@example.com", "US", "2024-02-07", "ACTIVE"),
    (1008, "Hannah Lee", "hannah.lee@example.com", "AU", "2024-02-11", "CHURNED"),
    (1009, "Ivan Petrov", "ivan.petrov@example.com", "DE", "2024-02-18", "ACTIVE"),
    (1010, "Julia Rossi", "julia.rossi@example.com", "GB", "2024-02-25", "ACTIVE"),
]

# table name -> (DDL, seed rows)
TABLES = {"customer": (CUSTOMER_DDL, CUSTOMER_SEED)}


def initialize_database(path: Path | str | None = None, reset: bool = False) -> Path:
    """Create and seed any missing target table. With reset=True, recreate them from the seed."""
    path = Path(path or target_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn, conn:  # one transaction
        for table, (ddl, seed) in TABLES.items():
            if reset:
                conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            elif conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
                continue
            conn.execute(ddl)
            conn.executemany(f'INSERT INTO "{table}" VALUES ({", ".join("?" * len(seed[0]))})', seed)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize the SQLite target database.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the target tables from the seed")
    args = parser.parse_args()
    print(f"Target database ready at {initialize_database(reset=args.reset)}")
