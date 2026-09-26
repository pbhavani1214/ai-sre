"""API tests for targets and upload runs. The LLM is replaced only at the provider boundary."""

import pytest
from fastapi.testclient import TestClient

from src.ai.provider import LLMError, LLMTimeoutError
from src.api.main import app, get_llm_provider, get_run_store, get_target_db
from src.runs.store import RunStore
from src.target.demo import DEMO_UPLOADS_DIR, SEED_CUSTOMERS, reset_demo_database
from tests.llm_stub import FailingProvider, StubProvider

client = TestClient(app)
BAD = (DEMO_UPLOADS_DIR / "customers_upload_bad.csv").read_bytes()
FIXED = (DEMO_UPLOADS_DIR / "customers_upload_fixed.csv").read_bytes()


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    db = str(reset_demo_database(tmp_path / "target.db"))
    runs = RunStore()
    app.dependency_overrides[get_target_db] = lambda: db
    app.dependency_overrides[get_run_store] = lambda: runs
    yield runs
    app.dependency_overrides.clear()


def use_llm(provider):
    app.dependency_overrides[get_llm_provider] = lambda: (lambda: provider)
    return provider


def upload(content=BAD, name="customers_upload_bad.csv", table="customers", **extra):
    return client.post("/api/runs", data={"target_table": table, **extra}, files={"file": (name, content, "text/csv")})


def error(r, status, code, field=None):
    assert r.status_code == status, r.text
    assert r.json()["detail"]["code"] == code
    assert r.json()["detail"]["field"] == field
    assert r.json()["detail"]["message"]


# --- targets -----------------------------------------------------------------------------------

def test_list_targets():
    assert client.get("/api/targets").json() == [
        {"name": "customers", "row_count": len(SEED_CUSTOMERS), "column_count": 6}]


def test_target_detail_comes_from_the_database():
    body = client.get("/api/targets/customers").json()
    assert body["ddl"].startswith("CREATE TABLE customers")
    assert body["primary_key"] == ["customer_id"]
    assert [c["name"] for c in body["check_constraints"]] == [
        "country_iso2", "signup_date_iso", "status_allowed", "email_format"]


def test_unknown_target_is_404():
    error(client.get("/api/targets/nope"), 404, "target_not_found")


def test_reset_restores_seed_rows():
    assert upload(FIXED).json()["status"] == "SUCCESS"
    assert client.get("/api/targets/customers").json()["row_count"] == len(SEED_CUSTOMERS) + 10
    assert client.post("/api/targets/reset").json()[0]["row_count"] == len(SEED_CUSTOMERS)


def test_demo_upload_files_are_served():
    r = client.get("/api/demo/uploads/customers_upload_bad.csv")
    assert r.status_code == 200 and r.content == BAD and r.headers["content-type"].startswith("text/csv")
    error(client.get("/api/demo/uploads/secrets.env"), 404, "file_not_found")


# --- runs --------------------------------------------------------------------------------------

def test_failed_run_is_created_with_evidence():
    r = upload()
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["run_id"].startswith("run_") and len(body["run_id"]) == 16
    assert body["created_at"].endswith("Z")
    assert body["status"] == "FAILED" and body["failed_stage"] == "validate"
    assert body["validation_summary"] == {"total_checks": 9, "passed_checks": 3, "failed_checks": 6}
    assert body["rows_loaded"] == 0 and body["target_rows_after"] == len(SEED_CUSTOMERS)
    assert body["pipeline_run"]["status"] == "FAILED"
    assert [s["name"] for s in body["pipeline_run"]["steps"]] == ["parse", "schema_check", "validate", "load"]
    assert body["row_issues"] and body["row_issues_truncated"] is False
    assert len(body["preview"]) == 12 and body["preview"][11]["customer_id"] == "CUST-1020"
    assert body["investigation"] is None and body["retry_comparison"] is None


def test_get_and_list_runs():
    created = upload().json()
    assert client.get(f"/api/runs/{created['run_id']}").json() == created
    second = upload(FIXED, "fixed.csv", retry_of=created["run_id"]).json()
    listed = client.get("/api/runs").json()
    assert [r["run_id"] for r in listed] == [second["run_id"], created["run_id"]]
    assert listed[0] == {
        "run_id": second["run_id"], "created_at": second["created_at"], "status": "SUCCESS", "failed_stage": None,
        "target_table": "customers", "file_name": "fixed.csv", "retry_of": created["run_id"], "row_count": 10,
        "rows_loaded": 10, "investigated": False}


def test_fail_fix_retry_success():
    bad = upload().json()
    good = upload(FIXED, "customers_upload_fixed.csv", retry_of=bad["run_id"])
    assert good.status_code == 201
    body = good.json()
    assert body["status"] == "SUCCESS" and body["rows_loaded"] == 10
    assert (body["target_rows_before"], body["target_rows_after"]) == (10, 20)
    assert body["retry_comparison"]["resolved_checks"] == sorted(
        r["name"] for r in bad["validation_results"] if r["status"] == "FAILED")
    assert client.get("/api/targets/customers").json()["row_count"] == 20


def test_unknown_run_is_404():
    error(client.get("/api/runs/run_000000000000"), 404, "run_not_found")


@pytest.mark.parametrize("content, status, code", [
    (b"", 422, "invalid_csv"),
    (b"customer_id,customer_id\n1,2\n", 422, "invalid_header"),
    ("customer_id\ncafé\n".encode("latin-1"), 422, "invalid_encoding"),
])
def test_unreadable_file_is_an_error_and_creates_no_run(isolated, content, status, code):
    error(upload(content), status, code, "file")
    assert isolated.list() == []


def test_file_too_large(monkeypatch):
    from src.runs import ingest
    monkeypatch.setattr(ingest, "MAX_UPLOAD_BYTES", 10)
    error(upload(), 413, "file_too_large", "file")


def test_unknown_target_table_on_upload():
    error(upload(table="orders"), 404, "target_not_found", "target_table")


def test_retry_of_unknown_run():
    error(upload(FIXED, retry_of="run_000000000000"), 404, "run_not_found", "retry_of")


def test_missing_fields_are_fastapi_422():
    r = client.post("/api/runs", data={"target_table": "customers"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)


# --- investigation -----------------------------------------------------------------------------

def test_investigation_receives_the_runs_real_evidence():
    llm = use_llm(StubProvider())
    run = upload().json()
    r = client.post(f"/api/runs/{run['run_id']}/investigate")
    assert r.status_code == 200, r.text
    ctx = llm.context()
    assert ctx["validation_results"] == run["validation_results"]
    assert ctx["execution_evidence"]["pipeline_run"] == run["pipeline_run"]
    assert ctx["target_table"]["ddl"].startswith("CREATE TABLE customers")
    assert "sample_rows" not in ctx["target_table"]  # no raw target rows go to the LLM
    assert ctx["upload"] == {"row_count": 12, "columns": run["columns"],
                             "null_counts": {c: 0 for c in run["columns"]}}
    ids = {e["id"] for e in ctx["available_evidence"]}
    assert {"validation.check_status_allowed", "validation.existing_key_conflicts", "pipeline.run_log",
            "pipeline.execution_summary", "dataset.target_table", "dataset.upload"} <= ids
    body = r.json()
    assert {"summary", "root_cause", "recommended_fix", "hypotheses", "investigation_trace"} <= set(body)


def test_investigation_is_saved_on_the_run():
    use_llm(StubProvider())
    run_id = upload().json()["run_id"]
    result = client.post(f"/api/runs/{run_id}/investigate").json()
    assert client.get(f"/api/runs/{run_id}").json()["investigation"] == result
    assert client.get("/api/runs").json()[0]["investigated"] is True


def test_successful_run_cannot_be_investigated():
    use_llm(StubProvider())
    run_id = upload(FIXED).json()["run_id"]
    error(client.post(f"/api/runs/{run_id}/investigate"), 409, "run_not_failed")


def test_investigating_unknown_run():
    use_llm(StubProvider())
    error(client.post("/api/runs/run_000000000000/investigate"), 404, "run_not_found")


def test_investigation_llm_errors_are_structured(monkeypatch):
    run_id = upload().json()["run_id"]
    use_llm(StubProvider("not json"))
    error(client.post(f"/api/runs/{run_id}/investigate"), 502, "llm_invalid_output")
    use_llm(FailingProvider(LLMTimeoutError("slow")))
    error(client.post(f"/api/runs/{run_id}/investigate"), 504, "llm_timeout")
    use_llm(FailingProvider(LLMError("down")))
    error(client.post(f"/api/runs/{run_id}/investigate"), 502, "llm_unavailable")
    use_llm(FailingProvider(RuntimeError("boom")))
    error(client.post(f"/api/runs/{run_id}/investigate"), 500, "internal_error")


def test_investigation_without_llm_key_is_503(monkeypatch):
    for k in ("LLM_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    run_id = upload().json()["run_id"]
    app.dependency_overrides.pop(get_llm_provider, None)
    error(client.post(f"/api/runs/{run_id}/investigate"), 503, "llm_not_configured")


def test_existing_demo_endpoints_still_work():
    assert client.get("/api/demo/scenario").json()["validation_summary"]["failed_checks"] == 6
    assert client.get("/api/demo/run").json()["pipeline_run"]["run_id"] == "run-2024-04-05-0200"
