"""Load, run-scoped AI investigation, retry and the full demo flow (CONTRACT.md 12-23).

The LLM is replaced only at the provider boundary (tests/llm_stub.py).
"""

import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from src.ai.provider import LLMError, LLMTimeoutError
from src.api.main import app, get_llm_provider, get_run_store, get_target_db
from src.config import DATA_DIR
from src.runs.ingest import parse_csv
from src.runs.service import load_run, validate_run
from src.runs.store import RunRecord, RunStore
from src.target.database import CUSTOMER_SEED, initialize_database
from src.target.discovery import discover_schema
from tests.llm_stub import FailingProvider, StubProvider, valid_llm_output

client = TestClient(app)
DEMO = DATA_DIR / "demo_uploads"
BAD, FIXED = (DEMO / "customer_bad.csv").read_bytes(), (DEMO / "customer_fixed.csv").read_bytes()
HEADER = "customer_id,name,email,country,signup_date,status\n"
SEED = len(CUSTOMER_SEED)


@pytest.fixture
def db(tmp_path):
    return str(initialize_database(tmp_path / "target.db"))


@pytest.fixture(autouse=True)
def api(db):
    runs = RunStore()
    app.dependency_overrides[get_target_db] = lambda: db
    app.dependency_overrides[get_run_store] = lambda: runs
    yield runs
    app.dependency_overrides.clear()


def use_llm(provider):
    app.dependency_overrides[get_llm_provider] = lambda: (lambda: provider)
    return provider


def upload(content, name="customer.csv"):
    data = content if isinstance(content, bytes) else content.encode()
    return client.post("/api/runs", data={"target_id": "customer"}, files={"file": (name, data, "text/csv")})


def retry(run_id, content, name="customer_fixed.csv"):
    data = content if isinstance(content, bytes) else content.encode()
    return client.post(f"/api/runs/{run_id}/retry", files={"file": (name, data, "text/csv")})


def rows(db):
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute("SELECT * FROM customer ORDER BY customer_id").fetchall()


def assert_error(r, status, code):
    assert r.status_code == status, r.text
    assert r.json()["detail"]["code"] == code and r.json()["detail"]["message"]


# --- transactional load ----------------------------------------------------------------------

def test_valid_run_is_appended_and_committed(db):
    before = rows(db)
    body = upload(FIXED, "customer_fixed.csv").json()
    assert body["status"] == "SUCCEEDED" and body["completed_at"]
    assert body["load_result"] == {"rows_loaded": 7, "target_table": "customer"}
    after = rows(db)
    assert len(after) == SEED + 7 and after[:SEED] == before  # APPEND: seed rows kept as they were
    assert after[-1] == (1017, "Quinn Taylor", "quinn.taylor@example.com", "AU", "2024-03-22", "ACTIVE")


def test_values_are_inserted_with_their_types_and_empty_as_null(db):
    upload(HEADER + "2001,Ann,ann@x.com,,,\n")
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT typeof(customer_id), country, status FROM customer WHERE customer_id = 2001"
                            ).fetchone() == ("integer", None, None)


def test_unexpected_columns_are_not_loaded(db):
    body = upload(HEADER.strip() + ",phone\n2001,Ann,ann@x.com,US,2024-01-01,ACTIVE,555\n").json()
    assert body["status"] == "SUCCEEDED" and len(rows(db)) == SEED + 1


def test_insert_error_rolls_back_everything_and_is_load_failed(db):
    # A database constraint the validation engine doesn't model (a trigger) rejects the 2nd row.
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("CREATE TRIGGER no_bob BEFORE INSERT ON customer WHEN NEW.name = 'Bob' "
                     "BEGIN SELECT RAISE(ABORT, 'Bob is not allowed'); END")
    before = rows(db)
    record = RunRecord("run_t", "customer", "customer", "c.csv",
                       parse_csv((HEADER + "2001,Ann,ann@x.com,,,\n2002,Bob,bob@x.com,,,\n").encode()))
    with closing(sqlite3.connect(db, isolation_level=None)) as conn:
        validate_run(record, discover_schema(conn, "customer"))
        load_run(record, conn)
    assert record.status == "LOAD_FAILED" and record.status_history[-2:] == ["LOADING", "LOAD_FAILED"]
    assert record.load_result is None and record.completed_at
    assert "Bob is not allowed" in record.load_error
    assert rows(db) == before  # Ann's row was rolled back too


def test_load_failed_through_the_api(db):
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("CREATE TRIGGER stop BEFORE INSERT ON customer BEGIN SELECT RAISE(ABORT, 'disk quota'); END")
    body = upload(FIXED).json()
    assert body["status"] == "LOAD_FAILED" and body["load_result"] is None and body["completed_at"]
    assert len(rows(db)) == SEED


def test_failed_validation_writes_nothing(db):
    before = rows(db)
    assert upload(BAD, "customer_bad.csv").json()["status"] == "FAILED_VALIDATION"
    assert rows(db) == before


def test_keys_already_in_the_target_fail_validation(db):
    assert upload(FIXED).json()["status"] == "SUCCEEDED"
    again = upload(FIXED).json()  # the same rows a second time
    assert again["status"] == "FAILED_VALIDATION"
    results = {r["name"]: r for r in again["validation_results"]}
    assert results["primary_key_uniqueness"]["metrics"]["existing_values"] == 7
    assert results["primary_key_uniqueness"]["evidence"][0] == (
        "[validation.primary_key_uniqueness.001] customer_id='1011' already exists in the target table (row 2)")
    assert results["unique_constraints"]["metrics"]["existing_values"] == 7
    assert len(rows(db)) == SEED + 7


# --- run-scoped AI investigation -------------------------------------------------------------

def test_investigation_uses_only_that_runs_evidence():
    llm = use_llm(StubProvider(valid_llm_output(
        observed_facts=["[validation.check_constraints.001] status='PENDING' is not an allowed value"],
        root_cause_evidence=["[validation.primary_key_uniqueness.001] customer_id='1013' appears 2 times"],
    )))
    other = upload(HEADER + "2001,Ann,ann@x.com,,,BAD\n").json()  # a different failed run
    run = upload(BAD, "customer_bad.csv").json()
    r = client.post(f"/api/runs/{run['run_id']}/investigate")
    assert r.status_code == 200, r.text
    ctx = llm.context()
    assert ctx["validation_results"] == run["validation_results"]
    assert ctx["execution_evidence"]["execution_summary"]["run_id"] == run["run_id"]
    assert other["run_id"] not in llm.prompts[0]
    ids = {e["id"] for e in ctx["available_evidence"]}
    assert {"validation.check_constraints", "validation.check_constraints.001", "validation.not_null.001",
            "dataset.target_table", "dataset.upload", "pipeline.run_log"} <= ids
    assert ctx["target_table"]["constraints"][-1]["allowed_values"] == ["ACTIVE", "INACTIVE", "CHURNED"]
    assert "Kevin Wong" not in llm.prompts[0]  # no raw rows, only the evidence lines and a profile
    body = r.json()
    assert body["run_id"] == run["run_id"]
    assert {"summary", "observed_facts", "hypotheses", "root_cause", "root_cause_evidence", "root_cause_reasoning",
            "recommended_fix", "regression_test", "investigation_trace", "evidence_warnings"} <= set(body)
    unknown = [w for w in body["evidence_warnings"] if "unknown" in w]
    assert not [w for w in unknown if "observed_facts" in w or "root_cause_evidence" in w]  # this run's IDs accepted
    assert any("validation.duplicate_customer_id" in w for w in unknown)  # an ID from another run is flagged


def test_investigation_is_stored_and_does_not_change_the_run():
    use_llm(StubProvider())
    run = upload(BAD).json()
    result = client.post(f"/api/runs/{run['run_id']}/investigate").json()
    stored = client.get(f"/api/runs/{run['run_id']}").json()
    assert stored["investigation"] == result
    assert {k: stored[k] for k in run if k != "investigation"} == {k: run[k] for k in run if k != "investigation"}


def test_succeeded_run_cannot_be_investigated():
    use_llm(StubProvider())
    run = upload(FIXED).json()
    assert_error(client.post(f"/api/runs/{run['run_id']}/investigate"), 409, "run_not_investigable")


def test_investigate_unknown_run():
    use_llm(StubProvider())
    assert_error(client.post("/api/runs/run_unknown/investigate"), 404, "run_not_found")


def test_llm_not_configured(monkeypatch):
    for k in ("LLM_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    run = upload(BAD).json()
    r = client.post(f"/api/runs/{run['run_id']}/investigate")
    assert r.json() == {"detail": {"code": "llm_not_configured", "message": "AI investigation is not configured.",
                                   "field": None}}
    assert r.status_code == 503


@pytest.mark.parametrize("provider, status, code", [
    (StubProvider("not json"), 502, "invalid_ai_response"),
    (FailingProvider(LLMTimeoutError("slow")), 504, "llm_timeout"),
    (FailingProvider(LLMError("down")), 502, "llm_provider_error"),
    (FailingProvider(RuntimeError("boom")), 500, "internal_error"),
])
def test_llm_errors(provider, status, code):
    run = upload(BAD).json()
    use_llm(provider)
    r = client.post(f"/api/runs/{run['run_id']}/investigate")
    assert_error(r, status, code)
    assert "Traceback" not in r.text and client.get(f"/api/runs/{run['run_id']}").json()["investigation"] is None


# --- retry -----------------------------------------------------------------------------------

def test_retry_creates_a_child_run_and_leaves_the_parent_unchanged(db):
    parent = upload(BAD, "customer_bad.csv").json()
    r = retry(parent["run_id"], FIXED)
    assert r.status_code == 201
    child = r.json()
    assert child["run_id"] != parent["run_id"] and child["parent_run_id"] == parent["run_id"]
    assert (child["target_id"], child["file_name"], child["status"]) == ("customer", "customer_fixed.csv", "SUCCEEDED")
    assert child["load_result"] == {"rows_loaded": 7, "target_table": "customer"}
    assert client.get(f"/api/runs/{parent['run_id']}").json() == parent
    assert len(rows(db)) == SEED + 7


def test_retry_that_still_fails_is_failed_validation_and_can_be_retried_again():
    parent = upload(BAD).json()
    child = retry(parent["run_id"], BAD, "still_bad.csv").json()
    assert child["status"] == "FAILED_VALIDATION" and child["parent_run_id"] == parent["run_id"]
    grandchild = retry(child["run_id"], FIXED).json()
    assert grandchild["status"] == "SUCCEEDED" and grandchild["parent_run_id"] == child["run_id"]


def test_succeeded_run_is_not_retryable():
    run = upload(FIXED).json()
    r = retry(run["run_id"], FIXED)
    assert_error(r, 409, "run_not_retryable")
    assert r.json()["detail"]["field"] == "run_id"


def test_retry_unknown_run_and_bad_file(api):
    assert_error(retry("run_unknown", FIXED), 404, "run_not_found")
    parent = upload(BAD).json()
    assert_error(retry(parent["run_id"], b"", "empty.csv"), 422, "empty_file")
    assert_error(retry(parent["run_id"], FIXED, "fixed.xlsx"), 422, "unsupported_file_type")
    assert len(api) == 1  # rejected files create no run


# --- the demo, end to end --------------------------------------------------------------------

def test_fail_investigate_fix_retry_succeed(db):
    use_llm(StubProvider())
    before = rows(db)

    bad = upload(BAD, "customer_bad.csv").json()
    assert bad["status"] == "FAILED_VALIDATION"
    assert sorted(r["name"] for r in bad["validation_results"] if r["status"] == "FAILED") == [
        "check_constraints", "data_type_compatibility", "not_null", "primary_key_uniqueness", "unique_constraints"]
    assert rows(db) == before

    investigation = client.post(f"/api/runs/{bad['run_id']}/investigate")
    assert investigation.status_code == 200

    fixed = retry(bad["run_id"], FIXED).json()
    assert fixed["status"] == "SUCCEEDED" and fixed["parent_run_id"] == bad["run_id"]
    assert len(rows(db)) == len(before) + 7

    final_bad = client.get(f"/api/runs/{bad['run_id']}").json()
    assert final_bad["status"] == "FAILED_VALIDATION" and final_bad["investigation"] == investigation.json()
    assert final_bad["validation_results"] == bad["validation_results"]  # evidence kept after investigation
    assert client.get(f"/api/runs/{fixed['run_id']}").json() == fixed
