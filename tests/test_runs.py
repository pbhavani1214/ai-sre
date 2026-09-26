"""Milestone 2: single CSV upload and run creation (CONTRACT.md, Run Creation / Run Response / GET Run)."""

import re

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_run_store, get_target_db
from src.runs import ingest, store as store_module
from src.runs.store import RunStore
from src.target.database import initialize_database

client = TestClient(app)

CSV = (b"customer_id,name,email,country,signup_date,status\n"
       b"101,Alice,alice@example.com,India,2026-09-01,ACTIVE\n"
       b"102,Bob,bob@example.com,India,2026-09-02,INACTIVE\n")


@pytest.fixture(autouse=True)
def runs(tmp_path):
    runs = RunStore()
    db = str(initialize_database(tmp_path / "target.db"))  # runs load data now: never touch data/target.db
    app.dependency_overrides[get_run_store] = lambda: runs
    app.dependency_overrides[get_target_db] = lambda: db
    yield runs
    app.dependency_overrides.clear()


def upload(content=CSV, name="customer.csv", target_id="customer"):
    return client.post("/api/runs", data={"target_id": target_id}, files={"file": (name, content, "text/csv")})


def assert_error(r, status, code, field="file"):
    assert r.status_code == status, r.text
    detail = r.json()["detail"]
    assert detail["code"] == code and detail["field"] == field and detail["message"]


# --- creating a run --------------------------------------------------------------------------

def test_valid_csv_creates_a_run(runs):
    r = upload()
    assert r.status_code == 201, r.text
    body = r.json()
    assert re.fullmatch(r"run_[0-9a-f]{12}", body["run_id"])
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", body["created_at"])
    # The run is validated and, with every check PASSED, appended to the target before the response.
    assert [v["name"] for v in body["validation_results"]] == [
        "required_columns", "unexpected_columns", "data_type_compatibility", "not_null",
        "primary_key_uniqueness", "unique_constraints", "check_constraints"]
    assert all(v["status"] == "PASSED" for v in body["validation_results"])
    assert body == {
        "run_id": body["run_id"], "parent_run_id": None, "database_id": "target", "target_id": "customer",
        "target_table": "customer",
        "file_name": "customer.csv", "status": "SUCCEEDED", "created_at": body["created_at"],
        "completed_at": body["completed_at"],
        "summary": {"rows_received": 2, "checks_total": 7, "checks_passed": 7, "checks_failed": 0},
        "validation_results": body["validation_results"],
        "load_result": {"rows_loaded": 2, "target_table": "customer"}, "investigation": None,
    }
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", body["completed_at"])
    assert len(runs) == 1


def test_uploaded_data_is_kept_internally_not_returned(runs):
    body = upload().json()
    record = runs.get(body["run_id"])
    assert record.upload.columns == ["customer_id", "name", "email", "country", "signup_date", "status"]
    assert record.upload.rows[1] == ["102", "Bob", "bob@example.com", "India", "2026-09-02", "INACTIVE"]
    assert record.upload.lines == [2, 3]
    assert "Alice" not in str(body)


def test_values_and_column_names_are_preserved_as_uploaded(runs):
    body = upload("\ufeff id , Name\n 7 ,\n\nNA,\"a, b\"\n".encode()).json()
    record = runs.get(body["run_id"])
    assert record.upload.columns == [" id ", " Name"]  # BOM removed, names otherwise untouched
    assert record.upload.rows == [[" 7 ", ""], ["NA", "a, b"]]
    assert record.upload.lines == [2, 4]  # blank line 3 skipped
    assert body["summary"]["rows_received"] == 2


def test_extension_check_is_case_insensitive():
    assert upload(name="CUSTOMER.CSV").status_code == 201


def test_get_run_returns_the_created_run():
    created = upload().json()
    r = client.get(f"/api/runs/{created['run_id']}")
    assert r.status_code == 200 and r.json() == created


# --- rejected uploads create no run ----------------------------------------------------------

def test_unknown_target(runs):
    assert_error(upload(target_id="orders"), 404, "target_not_found", "target_id")
    assert len(runs) == 0


@pytest.mark.parametrize("name", ["customer.xlsx", "customer.csv.txt", "customer", ""])
def test_unsupported_file_type(runs, name):
    r = client.post("/api/runs", data={"target_id": "customer"}, files={"file": (name, CSV, "text/csv")})
    if name == "":  # no file name at all: FastAPI doesn't treat it as a file upload
        assert r.status_code == 422
    else:
        assert_error(r, 422, "unsupported_file_type")
    assert len(runs) == 0


@pytest.mark.parametrize("content", [b"", b"   \n\n", b"customer_id,name\n", b"customer_id,name\n\n\n"])
def test_empty_file_or_no_data_rows(runs, content):
    assert_error(upload(content), 422, "empty_file")
    assert len(runs) == 0


@pytest.mark.parametrize("content", [b",,\n1,2,3\n", b"customer_id,,status\n1,2,3\n", b"\ncustomer_id\n1\n"])
def test_missing_header(runs, content):
    assert_error(upload(content), 422, "missing_header")
    assert len(runs) == 0


@pytest.mark.parametrize("content", [
    b"customer_id,name\n1,Alice,extra\n",  # too many fields
    b"customer_id,name\n1\n",  # too few fields
    b"customer_id,customer_id\n1,2\n",  # duplicate column name
    b'customer_id,name\n1,"unterminated\n',  # unclosed quote
    b"customer_id,name\n1,A\x00lice\n",  # NUL byte
])
def test_malformed_csv(runs, content):
    assert_error(upload(content), 422, "malformed_csv")
    assert len(runs) == 0


def test_non_utf8_is_invalid_file(runs):
    assert_error(upload("customer_id,name\n1,caf\u00e9\n".encode("latin-1")), 422, "invalid_file")
    assert len(runs) == 0


def test_file_larger_than_10_mb(runs):
    big = CSV + b"x" * (10 * 1024 * 1024)
    assert_error(upload(big), 413, "file_too_large")
    assert len(runs) == 0


def test_file_of_exactly_10_mb_is_accepted():
    row = b"103,Carol,carol@example.com,India,2026-09-03,ACTIVE\n"
    padding = ingest.MAX_UPLOAD_BYTES - len(CSV)
    content = CSV + row * (padding // len(row))
    content += b"\n" * (ingest.MAX_UPLOAD_BYTES - len(content))  # blank lines, skipped
    assert len(content) == ingest.MAX_UPLOAD_BYTES
    assert upload(content).status_code == 201


def test_missing_form_fields_are_rejected(runs):
    assert client.post("/api/runs", data={"target_id": "customer"}).status_code == 422
    assert client.post("/api/runs", files={"file": ("customer.csv", CSV, "text/csv")}).status_code == 422
    assert len(runs) == 0


# --- GET and retention -----------------------------------------------------------------------

def test_unknown_run():
    r = client.get("/api/runs/run_unknown")
    assert r.status_code == 404
    assert r.json() == {"detail": {"code": "run_not_found", "message": "Run 'run_unknown' was not found.",
                                   "field": "run_id"}}


def test_only_the_latest_20_runs_are_kept(runs):
    ids = [upload().json()["run_id"] for _ in range(store_module.MAX_RUNS + 1)]
    assert store_module.MAX_RUNS == 20 and len(runs) == 20
    assert client.get(f"/api/runs/{ids[0]}").status_code == 404
    assert all(client.get(f"/api/runs/{i}").status_code == 200 for i in ids[1:])
