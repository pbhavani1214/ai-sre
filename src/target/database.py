"""The demo SQLite target databases: the existing tables that uploaded data is loaded into.

Every SQLite file in TARGET_DB_DIR is a database the user can choose (see catalog.py); this module
only creates the demo ones. The table DDL below is the only place the demo schemas are written down.
Everything else (the API and the validation engine) reads them back from SQLite (see discovery.py).

Initialization is idempotent: a missing table is created and seeded, an existing one is left
untouched, so data survives restarts. To start over:

    python -m src.target.database --reset
"""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from src.config import target_db_dir, target_db_path

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

ORDERS_DDL = """CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_email TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL CHECK(currency IN ('USD', 'EUR', 'INR')),
    status TEXT CHECK(status IN ('PLACED', 'SHIPPED', 'CANCELLED')),
    order_date TEXT
)"""

ORDERS_SEED = [
    (5001, "alice.carter@example.com", 120.5, "USD", "SHIPPED", "2024-03-02"),
    (5002, "bob.singh@example.com", 89.0, "INR", "PLACED", "2024-03-05"),
    (5003, "chloe.martin@example.com", 42.75, "EUR", "SHIPPED", "2024-03-09"),
    (5004, "eva.schmidt@example.com", 310.0, "EUR", "CANCELLED", "2024-03-12"),
    (5005, "julia.rossi@example.com", 15.99, "EUR", "PLACED", "2024-03-15"),
]

PRODUCTS_DDL = """CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    category TEXT CHECK(category IN ('HARDWARE', 'SOFTWARE', 'SERVICE'))
)"""

PRODUCTS_SEED = [
    (1, "HW-100", "Edge Router", 249.0, "HARDWARE"),
    (2, "SW-200", "Monitoring Suite", 99.0, "SOFTWARE"),
    (3, "SV-300", "Onboarding Package", 499.0, "SERVICE"),
]

# table name -> (DDL, seed rows)
TABLES = {"customer": (CUSTOMER_DDL, CUSTOMER_SEED)}

# The demo databases created in TARGET_DB_DIR: database file stem -> its tables.
DEMO_DATABASES = {
    "crm": TABLES,
    "sales": {"orders": (ORDERS_DDL, ORDERS_SEED), "products": (PRODUCTS_DDL, PRODUCTS_SEED)},
}


def initialize_database(path: Path | str | None = None, reset: bool = False,
                        tables: dict | None = None) -> Path:
    """Create and seed any missing table (default: the CRM customer table). With reset=True, recreate them from
    the seed."""
    path = Path(path or target_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn, conn:  # one transaction
        for table, (ddl, seed) in (tables or TABLES).items():
            if reset:
                conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            elif conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
                continue
            conn.execute(ddl)
            conn.executemany(f'INSERT INTO "{table}" VALUES ({", ".join("?" * len(seed[0]))})', seed)
    return path


def initialize_demo_databases(directory: Path | str | None = None, reset: bool = False) -> Path:
    """Create (or, with reset=True, restore) every demo database in the database folder."""
    directory = Path(directory or target_db_dir())
    for name, tables in DEMO_DATABASES.items():
        initialize_database(directory / f"{name}.db", reset=reset, tables=tables)
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize the demo SQLite target databases.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the demo tables from the seed")
    args = parser.parse_args()
    print(f"Demo databases ready in {initialize_demo_databases(reset=args.reset)}")
    print(f"Default database ready at {initialize_database(reset=args.reset)}")
