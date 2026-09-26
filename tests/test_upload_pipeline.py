"""Upload pipeline: CSV reading, schema-derived validation, all-or-nothing load. No LLM involved."""

import sqlite3
from contextlib import closing

import pytest

from src.runs import ingest
from src.runs.ingest import UploadError, parse_csv
from src.runs.pipeline import run_pipeline
from src.target.demo import DEMO_UPLOADS_DIR, SEED_CUSTOMERS, reset_demo_database

HEADER = "customer_id,name,email,country,signup_date,status\n"
GOOD_ROW = "2001,New Person,new.person@example.com,US,2024-05-01,active\n"


@pytest.fixture
def db(tmp_path):
    return str(reset_demo_database(tmp_path / "target.db"))


def run(db, text, table="customers", retry_of=None):
    return run_pipeline(db, table, parse_csv(text.encode()), "upload.csv", "run_test", retry_of).detail


def results(detail):
    return {r["name"]: r for r in detail["validation_results"]}


def count(db, table="customers"):
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- reading the file ------------------------------------------------------------------------

def test_parse_keeps_strings_and_nulls_and_line_numbers():
    p = parse_csv("﻿ a , b \n1,\n\nNA,x\n".encode())
    assert p.columns == ["a", "b"]
    assert p.rows == [{"a": "1", "b": None}, {"a": "NA", "b": "x"}]
    assert p.lines == [2, 4]


@pytest.mark.parametrize("data, code", [
    (b"", "invalid_csv"),
    (b"a,b\n", "invalid_csv"),
    (b"a,a\n1,2\n", "invalid_header"),
    (b"a,\n1,2\n", "invalid_header"),
    (b"a,b\n1,2,3\n", "invalid_csv"),
    ("a\ncafé\n".encode("latin-1"), "invalid_encoding"),
])
def test_unreadable_files_are_rejected(data, code):
    with pytest.raises(UploadError) as e:
        parse_csv(data)
    assert e.value.code == code and e.value.status_code == 422 and e.value.field == "file"


def test_row_and_size_limits(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_UPLOAD_ROWS", 2)
    with pytest.raises(UploadError) as e:
        parse_csv(b"a\n1\n2\n3\n")
    assert e.value.code == "too_many_rows"
    import io
    with pytest.raises(UploadError) as e:
        ingest.read_limited(io.BytesIO(b"x" * 11), limit=10)
    assert e.value.code == "file_too_large" and e.value.status_code == 413


# --- success path ------------------------------------------------------------------------------

def test_valid_file_loads_all_rows(db):
    d = run(db, HEADER + GOOD_ROW)
    assert d["status"] == "SUCCESS" and d["failed_stage"] is None
    assert d["rows_loaded"] == 1
    assert (d["target_rows_before"], d["target_rows_after"]) == (len(SEED_CUSTOMERS), len(SEED_CUSTOMERS) + 1)
    assert count(db) == len(SEED_CUSTOMERS) + 1
    assert all(r["status"] == "PASSED" for r in d["validation_results"])
    assert [s["status"] for s in d["pipeline_run"]["steps"]] == ["SUCCESS"] * 4
    assert d["row_issues"] == []


def test_loaded_values_are_typed(db):
    run(db, HEADER + GOOD_ROW)
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT typeof(customer_id) FROM customers WHERE customer_id = 2001").fetchone() == ("integer",)


# --- validation failures, each derived from the table definition --------------------------------

def test_any_failure_writes_nothing(db):
    d = run(db, HEADER + GOOD_ROW + "2002,X,x@example.com,US,2024-05-01,pending\n")
    assert d["status"] == "FAILED" and d["failed_stage"] == "validate"
    assert d["rows_loaded"] == 0 and count(db) == len(SEED_CUSTOMERS)
    assert d["pipeline_run"]["steps"][-1] == {"name": "load", "status": "SKIPPED", "rows_in": 1, "rows_written": 0}


def test_not_null(db):
    d = run(db, HEADER + "2001,,a@example.com,US,2024-05-01,active\n")
    r = results(d)["not_null"]
    assert r["status"] == "FAILED" and r["metrics"]["null_values"] == {"name": 1}
    assert r["evidence"] == ["line 2: name is empty (the column is NOT NULL)"]


def test_type_conformance(db):
    r = results(run(db, HEADER + "ABC-1,X,a@example.com,US,2024-05-01,active\n"))["type_conformance"]
    assert r["status"] == "FAILED" and "customer_id='ABC-1' is not a valid INTEGER" in r["evidence"][0]


def test_duplicates_within_file(db):
    r = results(run(db, HEADER + GOOD_ROW + GOOD_ROW))["duplicate_keys_in_file"]
    assert r["status"] == "FAILED" and r["metrics"]["extra_rows"] == 2  # customer_id and email
    assert r["evidence"][0] == "customer_id=2001 appears 2 times in the file (lines 2, 3)"


def test_conflicts_with_rows_already_in_target(db):
    r = results(run(db, HEADER + "1001,A,alice.carter@example.com,US,2024-01-05,active\n"))["existing_key_conflicts"]
    assert r["status"] == "FAILED" and r["metrics"]["conflicts_by_key"] == {"customer_id": 1, "email": 1}


@pytest.mark.parametrize("row, check", [
    ("2001,X,x@example.com,USA,2024-05-01,active", "check_country_iso2"),
    ("2001,X,x@example.com,US,2024-02-30,active", "check_signup_date_iso"),
    ("2001,X,x@example.com,US,2024-05-01,Active", "check_status_allowed"),
    ("2001,X,x@example,US,2024-05-01,active", "check_email_format"),
])
def test_check_constraints_are_evaluated_by_sqlite(db, row, check):
    d = run(db, HEADER + row + "\n")
    assert [r["name"] for r in d["validation_results"] if r["status"] == "FAILED"] == [check]
    assert d["row_issues"][0]["line"] == 2 and d["row_issues"][0]["check"] == check


def test_schema_mismatch(db):
    d = run(db, "customer_id,name,email,country,signup_date,region\n2001,X,x@example.com,US,2024-05-01,NA\n")
    r = results(d)["schema_columns"]
    assert d["failed_stage"] == "schema_check"
    assert r["metrics"] == {"affected_records": 0, "missing_required_columns": 1, "unknown_columns": 1}
    assert any("required column 'status'" in e for e in r["evidence"])


def test_evidence_is_capped_but_row_issues_are_complete(db):
    rows = "".join(f"{3000 + i},X{i},x{i}@example.com,US,2024-05-01,bad\n" for i in range(8))
    d = run(db, HEADER + rows)
    r = results(d)["check_status_allowed"]
    assert len(r["evidence"]) == 6 and r["evidence"][-1] == "... and 3 more"
    assert r["metrics"]["affected_records"] == 8
    assert len([i for i in d["row_issues"] if i["check"] == "check_status_allowed"]) == 8


# --- generic tables and load-stage failures ----------------------------------------------------

def test_works_for_any_table(tmp_path):
    db = str(tmp_path / "shop.db")
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("CREATE TABLE products (sku TEXT PRIMARY KEY, price REAL NOT NULL CHECK (price > 0), "
                     "qty INTEGER DEFAULT 0)")
    d = run(db, "sku,price\nA1,9.5\nA2,-1\nA3,cheap\n", table="products")
    failed = {r["name"] for r in d["validation_results"] if r["status"] == "FAILED"}
    assert failed == {"type_conformance", "check_1"}
    d = run(db, "sku,price\nA1,9.5\n", table="products")
    assert d["status"] == "SUCCESS" and count(db, "products") == 1


def test_database_rejection_at_load_is_rolled_back_and_recorded(tmp_path):
    db = str(tmp_path / "fk.db")
    with closing(sqlite3.connect(db)) as conn:
        conn.executescript("CREATE TABLE country (code TEXT PRIMARY KEY);"
                           "CREATE TABLE city (name TEXT NOT NULL, code TEXT REFERENCES country(code));"
                           "INSERT INTO country VALUES ('US');")
    d = run(db, "name,code\nBoston,US\nParis,FR\n", table="city")
    assert all(r["status"] == "PASSED" for r in d["validation_results"])  # foreign keys aren't pre-validated
    assert d["status"] == "FAILED" and d["failed_stage"] == "load"
    assert "FOREIGN KEY constraint failed" in d["load_error"]
    assert d["rows_loaded"] == 0 and count(db, "city") == 0
    assert any("rolled back" in line for line in d["pipeline_run"]["logs"])


# --- the demo: fail -> fix -> retry -> success -------------------------------------------------

def test_demo_bad_file_fails_with_data_derived_evidence(db):
    d = run(db, (DEMO_UPLOADS_DIR / "customers_upload_bad.csv").read_text())
    assert d["status"] == "FAILED" and d["failed_stage"] == "validate"
    assert {r["name"] for r in d["validation_results"] if r["status"] == "FAILED"} == {
        "type_conformance", "duplicate_keys_in_file", "existing_key_conflicts",
        "check_signup_date_iso", "check_status_allowed", "check_email_format"}
    assert {i["line"] for i in d["row_issues"]} == {4, 7, 8, 9, 10, 11, 12, 13}
    assert count(db) == len(SEED_CUSTOMERS)


def test_demo_fixed_file_retry_succeeds(db):
    bad = run(db, (DEMO_UPLOADS_DIR / "customers_upload_bad.csv").read_text())
    good = run(db, (DEMO_UPLOADS_DIR / "customers_upload_fixed.csv").read_text(), retry_of=bad)
    assert good["status"] == "SUCCESS" and good["rows_loaded"] == 10
    assert good["retry_of"] == "run_test" and count(db) == len(SEED_CUSTOMERS) + 10
    cmp = good["retry_comparison"]
    assert cmp["previous_status"] == "FAILED" and cmp["still_failing_checks"] == cmp["new_failing_checks"] == []
    assert len(cmp["resolved_checks"]) == 6


def test_reloading_the_same_file_fails_on_existing_keys(db):
    fixed = (DEMO_UPLOADS_DIR / "customers_upload_fixed.csv").read_text()
    assert run(db, fixed)["status"] == "SUCCESS"
    again = run(db, fixed)
    assert again["status"] == "FAILED"
    assert results(again)["existing_key_conflicts"]["metrics"]["affected_records"] == 10
