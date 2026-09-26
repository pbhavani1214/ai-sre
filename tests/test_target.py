"""Milestone 1: SQLite target database, target discovery and schema discovery (CONTRACT.md)."""

import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_target_db
from src.target.database import CUSTOMER_SEED, initialize_database
from src.target.discovery import TableNotFound, discover_schema

client = TestClient(app)


@pytest.fixture
def db(tmp_path):
    path = str(initialize_database(tmp_path / "target.db"))
    app.dependency_overrides[get_target_db] = lambda: path
    yield path
    app.dependency_overrides.clear()


def rows(db, sql, *args):
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute(sql, args).fetchall()


def schema(db, table="customer"):
    with closing(sqlite3.connect(db)) as conn:
        return discover_schema(conn, table)


# --- database ----------------------------------------------------------------------------------

def test_database_initializes_with_seeded_customer_table(db):
    assert rows(db, "SELECT name FROM sqlite_master WHERE type = 'table'") == [("customer",)]
    assert rows(db, "SELECT COUNT(*) FROM customer") == [(len(CUSTOMER_SEED),)]


def test_initialization_is_repeatable_and_keeps_existing_data(db):
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("INSERT INTO customer (customer_id, name, email) VALUES (2001, 'New', 'new@example.com')")
    initialize_database(db)
    assert rows(db, "SELECT COUNT(*) FROM customer") == [(len(CUSTOMER_SEED) + 1,)]


def test_reset_restores_the_seed(db):
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("DELETE FROM customer")
    initialize_database(db, reset=True)
    assert rows(db, "SELECT COUNT(*) FROM customer") == [(len(CUSTOMER_SEED),)]


def test_initialization_adds_missing_tables_without_touching_others(tmp_path):
    path = tmp_path / "existing.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE other (x INTEGER)")
        conn.execute("INSERT INTO other VALUES (1)")
    initialize_database(path)
    assert rows(path, "SELECT x FROM other") == [(1,)]
    assert rows(path, "SELECT COUNT(*) FROM customer") == [(len(CUSTOMER_SEED),)]


def test_database_enforces_the_seeded_constraints(db):
    with closing(sqlite3.connect(db)) as conn, pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute("INSERT INTO customer VALUES (2001, 'X', 'x@example.com', 'US', '2024-05-01', 'PENDING')")


# --- discovery ---------------------------------------------------------------------------------

def test_integer_primary_key_is_not_nullable(db):
    # Regression: PRAGMA table_info reports notnull=0 for INTEGER PRIMARY KEY.
    assert rows(db, "SELECT \"notnull\", pk FROM pragma_table_info('customer') WHERE name = 'customer_id'") == [(0, 1)]
    cid = next(c for c in schema(db)["columns"] if c["name"] == "customer_id")
    assert cid == {"name": "customer_id", "data_type": "INTEGER", "nullable": False, "primary_key": True,
                   "unique": False}


def test_unique_comes_from_index_metadata_not_column_names(tmp_path):
    path = tmp_path / "t.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE t (email TEXT, code TEXT, a TEXT, b TEXT, UNIQUE (a, b))")
        conn.execute("CREATE UNIQUE INDEX t_code ON t (code)")
    s = schema(path, "t")
    assert {c["name"]: c["unique"] for c in s["columns"]} == {"email": False, "code": True, "a": False, "b": False}
    assert sorted(c["columns"] for c in s["constraints"] if c["type"] == "UNIQUE") == [["a", "b"], ["code"]]


def test_check_allowed_values_with_quotes_and_unparsed_checks(tmp_path):
    path = tmp_path / "t.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE t (s TEXT CHECK (s IN ('a', 'it''s', 'CHECK(x)')), n INTEGER CHECK (n > 0))")
    checks = [c for c in schema(path, "t")["constraints"] if c["type"] == "CHECK"]
    assert checks == [
        {"type": "CHECK", "columns": ["s"], "allowed_values": ["a", "it's", "CHECK(x)"],
         "description": "s must contain an allowed value"},
        {"type": "CHECK", "columns": [], "description": "CHECK (n > 0)"},
    ]


def test_unknown_table_raises(db):
    with pytest.raises(TableNotFound):
        schema(db, "nope")


# --- API ---------------------------------------------------------------------------------------

def test_list_targets(db):
    r = client.get("/api/targets")
    assert r.status_code == 200
    assert r.json() == {"targets": [{
        "target_id": "customer", "table_name": "customer", "display_name": "Customer",
        "description": "Customer master data", "database_type": "sqlite", "database_id": "target"}]}


def test_target_schema_columns(db):
    r = client.get("/api/targets/customer")
    assert r.status_code == 200
    body = r.json()
    assert (body["target_id"], body["table_name"], body["database_type"]) == ("customer", "customer", "sqlite")
    cols = {c["name"]: c for c in body["columns"]}
    assert list(cols) == ["customer_id", "name", "email", "country", "signup_date", "status"]
    assert cols["customer_id"]["primary_key"] and not cols["customer_id"]["nullable"]
    assert cols["email"]["unique"] and not cols["name"]["unique"]
    assert not cols["name"]["nullable"] and not cols["email"]["nullable"]
    assert all(cols[c]["nullable"] for c in ("country", "signup_date", "status"))
    assert all(c["data_type"] in ("INTEGER", "TEXT") for c in body["columns"])


def test_target_schema_constraints_match_contract(db):
    assert client.get("/api/targets/customer").json()["constraints"] == [
        {"type": "PRIMARY_KEY", "columns": ["customer_id"], "description": "customer_id must be unique and non-null"},
        {"type": "UNIQUE", "columns": ["email"], "description": "email must be unique"},
        {"type": "NOT_NULL", "columns": ["name", "email"], "description": "Required fields cannot be null"},
        {"type": "CHECK", "columns": ["status"], "allowed_values": ["ACTIVE", "INACTIVE", "CHURNED"],
         "description": "status must contain an allowed value"},
    ]


def test_schema_is_discovered_not_hardcoded(db):
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("ALTER TABLE customer ADD COLUMN tier TEXT NOT NULL DEFAULT 'STANDARD'")
    body = client.get("/api/targets/customer").json()
    assert body["columns"][-1] == {"name": "tier", "data_type": "TEXT", "nullable": False, "primary_key": False,
                                   "unique": False}
    assert next(c for c in body["constraints"] if c["type"] == "NOT_NULL")["columns"] == ["name", "email", "tier"]


def test_unknown_target_is_404(db):
    r = client.get("/api/targets/unknown")
    assert r.status_code == 404
    assert r.json() == {"detail": {"code": "target_not_found", "message": "Target 'unknown' was not found.",
                                   "field": "target_id"}}
