"""Milestone 3: deterministic, target-aware validation (CONTRACT.md, Validation Rules / Validation Result).

Every expected rule below comes from a table created in the test; no table-specific name is known
to the engine.
"""

import re
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_run_store, get_target_db
from src.config import DATA_DIR
from src.runs.ingest import parse_csv
from src.runs.service import validate_run
from src.runs.store import RunRecord, RunStore
from src.runs.validation import CHECK_NAMES, validate_upload
from src.target.database import CUSTOMER_SEED, initialize_database
from src.target.discovery import discover_schema

client = TestClient(app)
HEADER = "customer_id,name,email,country,signup_date,status\n"
GOOD = HEADER + ("101,Alice,alice@example.com,India,2026-09-01,ACTIVE\n"
                 "102,Bob,bob@example.com,India,2026-09-02,INACTIVE\n")
DEMO = DATA_DIR / "demo_uploads"


@pytest.fixture
def db(tmp_path):
    return str(initialize_database(tmp_path / "target.db"))


@pytest.fixture
def api(db):
    runs = RunStore()
    app.dependency_overrides[get_target_db] = lambda: db
    app.dependency_overrides[get_run_store] = lambda: runs
    yield runs
    app.dependency_overrides.clear()


def schema_of(db, table="customer"):
    with closing(sqlite3.connect(db)) as conn:
        return discover_schema(conn, table)


def make_table(tmp_path, ddl):
    path = str(tmp_path / "custom.db")
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(ddl)
    return path


def validate(db, csv, table="customer"):
    return {r["name"]: r for r in validate_upload(schema_of(db, table), parse_csv(csv.encode()))}


def failed(results):
    return sorted(n for n, r in results.items() if r["status"] == "FAILED")


def upload(content, name="customer.csv"):
    data = content if isinstance(content, bytes) else content.encode()
    return client.post("/api/runs", data={"target_id": "customer"}, files={"file": (name, data, "text/csv")})


# --- all checks, clean file ------------------------------------------------------------------

def test_clean_file_passes_every_check(db):
    results = validate(db, GOOD)
    assert list(results) == list(CHECK_NAMES)
    assert all(r["status"] == "PASSED" and r["severity"] == "INFO" and r["evidence"] == [] for r in results.values())


def test_result_shape_matches_contract(db):
    for r in validate(db, GOOD).values():
        assert set(r) == {"name", "status", "severity", "summary", "metrics", "evidence"}
        assert r["status"] in {"PASSED", "FAILED", "WARNING", "SKIPPED"}
        assert r["severity"] in {"INFO", "WARNING", "ERROR"}


# --- A. required_columns ---------------------------------------------------------------------

def test_required_column_missing(db):
    r = validate(db, "customer_id,email,country\n101,a@example.com,IN\n")["required_columns"]
    assert r["status"] == "FAILED" and r["severity"] == "ERROR"
    assert r["evidence"] == ["[validation.required_columns.001] required column `name` is missing from the CSV"]
    assert r["metrics"] == {"required_columns": 3, "missing_columns": 1}


def test_optional_columns_may_be_omitted(db):
    assert validate(db, "customer_id,name,email\n101,A,a@example.com\n")["required_columns"]["status"] == "PASSED"


def test_not_null_column_with_default_is_not_required(tmp_path):
    path = make_table(tmp_path, "CREATE TABLE t (id INTEGER PRIMARY KEY, tier TEXT NOT NULL DEFAULT 'STD')")
    assert validate(path, "id\n1\n", "t")["required_columns"]["status"] == "PASSED"


def test_integer_primary_key_is_required(db):
    # INTEGER PRIMARY KEY reports notnull=0 in PRAGMA; discovery marks it non-nullable, so it's required.
    r = validate(db, "name,email\nA,a@example.com\n")["required_columns"]
    assert r["status"] == "FAILED" and "`customer_id`" in r["evidence"][0]


# --- B. unexpected_columns -------------------------------------------------------------------

def test_exact_columns_pass(db):
    assert validate(db, GOOD)["unexpected_columns"]["status"] == "PASSED"


def test_extra_column_is_reported_as_warning_and_does_not_block(db):
    results = validate(db, HEADER.strip() + ",phone_number\n101,A,a@example.com,IN,2026-09-01,ACTIVE,555\n")
    r = results["unexpected_columns"]
    assert r["status"] == "WARNING" and r["severity"] == "WARNING"  # CONTRACT.md 8.2
    assert r["evidence"] == ["[validation.unexpected_columns.001] unexpected column `phone_number` is not in the "
                             "target table and would not be loaded"]
    assert failed(results) == []


# --- C. data_type_compatibility --------------------------------------------------------------

def test_valid_and_invalid_integer(db):
    assert validate(db, GOOD)["data_type_compatibility"]["status"] == "PASSED"
    r = validate(db, HEADER + "ABC,A,a@example.com,IN,2026-09-01,ACTIVE\n")["data_type_compatibility"]
    assert r["status"] == "FAILED"
    assert r["evidence"] == ["[validation.data_type_compatibility.001] customer_id='ABC' is not a valid INTEGER "
                             "(column type INTEGER) at row 2"]


@pytest.mark.parametrize("value, ok", [("12.5", True), ("-3", True), ("1e3", True), (".5", True),
                                       ("12,5", False), ("abc", False), ("nan", False), (" 1", False)])
def test_real_values(tmp_path, value, ok):
    path = make_table(tmp_path, "CREATE TABLE m (id INTEGER PRIMARY KEY, amount REAL)")
    r = validate(path, f'id,amount\n1,"{value}"\n', "m")["data_type_compatibility"]
    assert r["status"] == ("PASSED" if ok else "FAILED")


@pytest.mark.parametrize("value", ["1.0", "1 ", "+-1", "0x10"])
def test_integer_rejects_non_integers_without_converting(db, value):
    r = validate(db, HEADER + f'"{value}",A,a@example.com,IN,2026-09-01,ACTIVE\n')["data_type_compatibility"]
    assert r["status"] == "FAILED"


def test_text_accepts_anything_and_empty_is_left_to_not_null(db):
    r = validate(db, HEADER + "101,12345,a@example.com,,,\n")
    assert r["data_type_compatibility"]["status"] == "PASSED"


# --- D. not_null -----------------------------------------------------------------------------

def test_not_null(db):
    assert validate(db, GOOD)["not_null"]["status"] == "PASSED"
    r = validate(db, HEADER + "101,Alice,alice@example.com,IN,,\n,Bob,,IN,,\n")["not_null"]
    assert r["status"] == "FAILED"
    assert r["evidence"] == [
        "[validation.not_null.001] `customer_id` is empty (the column does not allow null) at row 3",
        "[validation.not_null.002] `email` is empty (the column does not allow null) at row 3",
    ]
    assert r["metrics"]["affected_rows"] == 1 and r["metrics"]["null_values"] == 2


def test_nullable_columns_may_be_empty(db):
    assert validate(db, HEADER + "101,A,a@example.com,,,\n")["not_null"]["status"] == "PASSED"


# --- E. primary_key_uniqueness ---------------------------------------------------------------

def test_duplicate_primary_key(db):
    r = validate(db, HEADER + "101,A,a@x.com,,,\n102,B,b@x.com,,,\n101,C,c@x.com,,,\n")["primary_key_uniqueness"]
    assert r["status"] == "FAILED"
    assert r["evidence"] == ["[validation.primary_key_uniqueness.001] customer_id='101' appears 2 times (rows 2, 4)"]
    assert r["metrics"] == {"affected_rows": 2, "duplicate_values": 1}


def test_integer_keys_compare_like_sqlite(db):
    r = validate(db, HEADER + "101,A,a@x.com,,,\n0101,B,b@x.com,,,\n")["primary_key_uniqueness"]
    assert r["status"] == "FAILED"


def test_composite_primary_key(tmp_path):
    path = make_table(tmp_path, "CREATE TABLE ol (order_id INTEGER, line INTEGER, PRIMARY KEY (order_id, line))")
    r = validate(path, "order_id,line\n1,1\n1,2\n1,1\n", "ol")["primary_key_uniqueness"]
    assert r["evidence"] == ["[validation.primary_key_uniqueness.001] (order_id, line)=('1', '1') appears 2 times "
                             "(rows 2, 4)"]


def test_table_without_primary_key_is_skipped(tmp_path):
    path = make_table(tmp_path, "CREATE TABLE logs (msg TEXT)")
    assert validate(path, "msg\nhi\n", "logs")["primary_key_uniqueness"]["status"] == "SKIPPED"


# --- F. unique_constraints -------------------------------------------------------------------

def test_duplicate_unique_value(db):
    assert validate(db, GOOD)["unique_constraints"]["status"] == "PASSED"
    r = validate(db, HEADER + "101,A,a@x.com,,,\n102,B,a@x.com,,,\n")["unique_constraints"]
    assert r["status"] == "FAILED"
    assert r["evidence"] == ["[validation.unique_constraints.001] email='a@x.com' appears 2 times (rows 2, 3)"]


def test_composite_unique_index(tmp_path):
    path = make_table(tmp_path, "CREATE TABLE s (id INTEGER PRIMARY KEY, a TEXT, b TEXT, UNIQUE (a, b))")
    results = validate(path, "id,a,b\n1,x,y\n2,x,z\n3,x,y\n", "s")
    assert results["unique_constraints"]["evidence"] == [
        "[validation.unique_constraints.001] (a, b)=('x', 'y') appears 2 times (rows 2, 4)"]


# --- G. check_constraints --------------------------------------------------------------------

def test_check_allowed_and_invalid_values(db):
    assert validate(db, GOOD)["check_constraints"]["status"] == "PASSED"
    r = validate(db, HEADER + "101,A,a@x.com,,,PENDING\n102,B,b@x.com,,,active\n103,C,c@x.com,,,\n")[
        "check_constraints"]
    assert r["status"] == "FAILED"
    assert r["evidence"] == [
        "[validation.check_constraints.001] status='PENDING' is not an allowed value (ACTIVE, INACTIVE, CHURNED) at row 2",
        "[validation.check_constraints.002] status='active' is not an allowed value (ACTIVE, INACTIVE, CHURNED) at row 3",
    ]  # case-sensitive, like SQLite's IN; the empty value (NULL) satisfies the CHECK


def test_allowed_values_come_from_the_database(tmp_path):
    path = make_table(tmp_path, "CREATE TABLE customer (customer_id INTEGER PRIMARY KEY, "
                                "status TEXT CHECK (status IN ('GOLD', 'SILVER')))")
    results = validate(path, "customer_id,status\n1,ACTIVE\n2,GOLD\n", "customer")
    assert results["check_constraints"]["evidence"] == [
        "[validation.check_constraints.001] status='ACTIVE' is not an allowed value (GOLD, SILVER) at row 2"]


def test_unparsed_check_is_skipped_not_invented(tmp_path):
    path = make_table(tmp_path, "CREATE TABLE p (id INTEGER PRIMARY KEY, price REAL CHECK (price > 0))")
    r = validate(path, "id,price\n1,-5\n", "p")["check_constraints"]
    assert r["status"] == "SKIPPED" and "CHECK (price > 0)" in r["summary"]


# --- H. evidence -----------------------------------------------------------------------------

def test_evidence_ids_are_sequential_and_capped(db):
    rows = "".join(f"{200 + i},N{i},n{i}@x.com,,,BAD\n" for i in range(8))
    r = validate(db, HEADER + rows)["check_constraints"]
    assert [re.match(r"\[(\S+)\]", e).group(1) for e in r["evidence"]] == [
        f"validation.check_constraints.{i:03d}" for i in range(1, 6)]
    assert r["metrics"]["affected_rows"] == 8 and r["metrics"]["invalid_values"] == 8  # totals stay complete
    assert "8 value(s)" in r["summary"]


def test_evidence_never_contains_unrelated_row_data(db):
    results = validate(db, HEADER + "101,Secret Person,secret@x.com,IN,2026-09-01,PENDING\n")
    text = str([r["evidence"] for r in results.values()])
    assert "Secret Person" not in text and "secret@x.com" not in text and "PENDING" in text


# --- I. run lifecycle ------------------------------------------------------------------------

def test_lifecycle_failed_validation(db):
    record = RunRecord("run_x", "customer", "customer", "c.csv",
                       parse_csv((HEADER + "ABC,,a@x.com,,,\n").encode()))
    validate_run(record, schema_of(db))
    assert record.status_history == ["CREATED", "VALIDATING", "FAILED_VALIDATION"]
    assert record.completed_at is not None and record.load_result is None


def test_lifecycle_passing_validation_stops_before_loading(db):
    record = RunRecord("run_y", "customer", "customer", "c.csv", parse_csv(GOOD.encode()))
    validate_run(record, schema_of(db))
    assert record.status_history == ["CREATED", "VALIDATING", "LOADING"]
    assert record.completed_at is None and record.load_result is None  # not loaded, not SUCCEEDED


def test_only_created_runs_can_be_validated(db):
    record = RunRecord("run_z", "customer", "customer", "c.csv", parse_csv(GOOD.encode()))
    validate_run(record, schema_of(db))
    with pytest.raises(ValueError):
        validate_run(record, schema_of(db))


def test_api_failed_validation_run(api):
    r = upload((DEMO / "customer_bad.csv").read_bytes(), "customer_bad.csv")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "FAILED_VALIDATION" and body["completed_at"] and body["load_result"] is None
    assert body["summary"] == {"rows_received": 7, "checks_total": 7, "checks_passed": 2, "checks_failed": 5}
    assert client.get(f"/api/runs/{body['run_id']}").json() == body


def test_api_passing_run(api):
    body = upload((DEMO / "customer_fixed.csv").read_bytes(), "customer_fixed.csv").json()
    assert body["status"] == "SUCCEEDED" and body["completed_at"]  # validated, then loaded
    assert body["load_result"] == {"rows_loaded": 7, "target_table": "customer"}
    assert body["summary"] == {"rows_received": 7, "checks_total": 7, "checks_passed": 7, "checks_failed": 0}


def test_demo_bad_file_failures_come_from_the_rules(db):
    results = validate(db, (DEMO / "customer_bad.csv").read_text())
    assert failed(results) == ["check_constraints", "data_type_compatibility", "not_null",
                               "primary_key_uniqueness", "unique_constraints"]
    evidence = [e for r in results.values() for e in r["evidence"]]
    assert evidence == [
        "[validation.data_type_compatibility.001] customer_id='CUST-1016' is not a valid INTEGER (column type INTEGER) at row 7",
        "[validation.not_null.001] `name` is empty (the column does not allow null) at row 3",
        "[validation.primary_key_uniqueness.001] customer_id='1013' appears 2 times (rows 4, 5)",
        "[validation.unique_constraints.001] email='oscar.diaz@example.com' appears 2 times (rows 6, 8)",
        "[validation.check_constraints.001] status='PENDING' is not an allowed value (ACTIVE, INACTIVE, CHURNED) at row 6",
        "[validation.check_constraints.002] status='active' is not an allowed value (ACTIVE, INACTIVE, CHURNED) at row 8",
    ]


# --- J. no target mutation -------------------------------------------------------------------

def test_validation_never_writes_to_the_target(api, db):
    def snapshot():
        with closing(sqlite3.connect(db)) as conn:
            return conn.execute("SELECT * FROM customer ORDER BY customer_id").fetchall()

    before = snapshot()
    assert len(before) == len(CUSTOMER_SEED)
    upload((DEMO / "customer_bad.csv").read_bytes(), "customer_bad.csv")  # FAILED_VALIDATION: nothing loaded
    record = RunRecord("run_v", "customer", "customer", "c.csv",
                       parse_csv((DEMO / "customer_fixed.csv").read_bytes()))
    validate_run(record, schema_of(db))  # validation alone never writes, even when every check passes
    assert record.status == "LOADING"
    assert snapshot() == before


# --- anti-hardcoding and determinism --------------------------------------------------------

def test_same_engine_validates_a_different_table_from_its_metadata(tmp_path):
    path = make_table(tmp_path, "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, amount REAL NOT NULL, "
                                "description TEXT)")
    ok = validate(path, "order_id,amount,description\n1,19.99,Book\n2,5,\n", "orders")
    assert failed(ok) == []
    assert ok["required_columns"]["summary"] == "All 2 required column(s) are present"
    assert ok["unique_constraints"]["status"] == "SKIPPED" and ok["check_constraints"]["status"] == "SKIPPED"

    bad = validate(path, "order_id,description,customer_id\nX1,Pen,7\n1,Cup,8\n1,Mug,9\n", "orders")
    assert failed(bad) == ["data_type_compatibility", "primary_key_uniqueness", "required_columns"]
    assert bad["required_columns"]["evidence"] == [
        "[validation.required_columns.001] required column `amount` is missing from the CSV"]
    assert bad["data_type_compatibility"]["evidence"] == [
        "[validation.data_type_compatibility.001] order_id='X1' is not a valid INTEGER (column type INTEGER) at row 2"]
    assert bad["unexpected_columns"]["status"] == "WARNING" and "`customer_id`" in bad["unexpected_columns"]["evidence"][0]


def test_same_csv_same_target_gives_identical_results(api):
    content = (DEMO / "customer_bad.csv").read_bytes()
    first, second = upload(content).json(), upload(content).json()
    assert first["run_id"] != second["run_id"]
    for key in ("status", "summary", "validation_results", "load_result"):
        assert first[key] == second[key]
