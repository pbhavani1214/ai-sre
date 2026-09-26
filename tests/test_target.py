"""Target database: demo setup and reading a table's definition back from SQLite."""

import sqlite3
from contextlib import closing

import pytest

from src.target.demo import SEED_CUSTOMERS, ensure_demo_database, reset_demo_database
from src.target.introspect import TargetNotFound, affinity, check_constraints, describe_table, list_tables


@pytest.fixture
def db(tmp_path):
    return str(reset_demo_database(tmp_path / "target.db"))


def test_demo_database_has_seeded_customers_table(db):
    with closing(sqlite3.connect(db)) as conn:
        assert list_tables(conn) == ["customers"]
        t = describe_table(conn, "customers")
    assert t["row_count"] == len(SEED_CUSTOMERS)
    assert [c["name"] for c in t["columns"]] == ["customer_id", "name", "email", "country", "signup_date", "status"]
    assert t["primary_key"] == ["customer_id"]
    assert t["unique_keys"] == [["customer_id"], ["email"]]
    assert t["ddl"].startswith("CREATE TABLE customers")
    assert len(t["sample_rows"]) == 3


def test_columns_carry_type_nullability_and_keys(db):
    with closing(sqlite3.connect(db)) as conn:
        cols = {c["name"]: c for c in describe_table(conn, "customers")["columns"]}
    assert cols["customer_id"]["affinity"] == "INTEGER" and cols["customer_id"]["primary_key"]
    assert cols["email"]["unique"] and cols["email"]["not_null"]
    assert cols["name"]["affinity"] == "TEXT" and not cols["name"]["unique"]


def test_check_constraints_are_read_from_ddl(db):
    with closing(sqlite3.connect(db)) as conn:
        checks = describe_table(conn, "customers")["check_constraints"]
    assert [c["name"] for c in checks] == ["country_iso2", "signup_date_iso", "status_allowed", "email_format"]
    assert checks[2]["expression"] == "status IN ('active', 'inactive', 'churned')"


def test_check_parser_handles_unnamed_nested_and_quoted():
    ddl = """CREATE TABLE t (
        a INTEGER CHECK (a > 0 AND (a < 10 OR a = 99)),
        b TEXT CHECK (b <> 'CHECK (x)'), -- CHECK (not_a_constraint)
        "c d" TEXT, CONSTRAINT "named one" CHECK ("c d" IN ('x', ')')),
        checked INTEGER
    )"""
    assert check_constraints(ddl) == [
        {"name": "check_1", "expression": "a > 0 AND (a < 10 OR a = 99)"},
        {"name": "check_2", "expression": "b <> 'CHECK (x)'"},
        {"name": "named one", "expression": "\"c d\" IN ('x', ')')"},
    ]


def test_affinity_rules():
    assert [affinity(t) for t in ("INTEGER", "BIGINT", "VARCHAR(20)", "", "DOUBLE", "DATE", "DECIMAL(10,2)")] == \
        ["INTEGER", "INTEGER", "TEXT", "BLOB", "REAL", "NUMERIC", "NUMERIC"]


def test_unknown_table_raises(db):
    with closing(sqlite3.connect(db)) as conn, pytest.raises(TargetNotFound):
        describe_table(conn, "nope")


def test_ensure_never_touches_an_existing_file(tmp_path):
    path = tmp_path / "other.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE products (sku TEXT PRIMARY KEY)")
    ensure_demo_database(path)
    with closing(sqlite3.connect(path)) as conn:
        assert list_tables(conn) == ["products"]
    assert list_tables(sqlite3.connect(ensure_demo_database(tmp_path / "new.db"))) == ["customers"]


def test_reset_restores_seed_rows(db):
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("DELETE FROM customers")
    reset_demo_database(db)
    with closing(sqlite3.connect(db)) as conn:
        assert describe_table(conn, "customers")["row_count"] == len(SEED_CUSTOMERS)
