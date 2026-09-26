"""Tests for the deterministic validation suite and GET /api/demo/scenario."""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_llm_provider
from src.data.scenario import build_source, load_scenario, simulate_pipeline
from src.validation import suite
from src.validation.suite import (
    MAX_EVIDENCE,
    check_duplicate_customer_id,
    check_invalid_email,
    check_invalid_status,
    check_missing_target_ids,
    check_null_customer_id,
    check_record_count,
    run_demo_validation_suite,
    run_validation_suite,
)

RESULT_KEYS = {"name", "status", "severity", "summary", "metrics", "evidence"}


def customers(rows):
    """rows: list of (customer_id, email, status). Builds a clean customer frame."""
    return pd.DataFrame(
        [{"customer_id": cid, "name": f"n{i}", "email": email, "country": "US", "status": status}
         for i, (cid, email, status) in enumerate(rows)]
    )


CLEAN = customers([("1", "a@x.com", "active"), ("2", "b@x.com", "inactive"), ("3", "c@x.com", "churned")])


# --- each of the six checks: passes on clean data, fails with real evidence on bad data ---

@pytest.mark.parametrize("check", [
    check_record_count, check_null_customer_id, check_duplicate_customer_id,
    check_missing_target_ids, check_invalid_email, check_invalid_status,
])
def test_every_check_passes_on_clean_data(check):
    r = check(CLEAN, CLEAN.copy())
    assert r.status == "PASSED" and r.evidence == []
    assert set(r.to_dict()) == RESULT_KEYS


def test_record_count_fails_and_uses_execution_evidence():
    run = {"steps": [{"name": "filter", "rows_in": 3, "rows_out": 2}, {"name": "noop", "rows_in": 2, "rows_out": 2}]}
    r = check_record_count(CLEAN, CLEAN.iloc[:2], run)
    assert r.status == "FAILED" and r.metrics["difference"] == -1 and r.metrics["affected_records"] == 1
    assert "fewer" in r.summary
    assert "pipeline step 'filter': 3 rows in, 2 rows out" in r.evidence
    assert not any("noop" in e for e in r.evidence)  # unchanged steps are not evidence


def test_null_customer_id_fails():
    target = customers([("1", "a@x.com", "active"), (None, "b@x.com", "active"), ("", "c@x.com", "active")])
    r = check_null_customer_id(CLEAN, target)
    assert r.status == "FAILED" and r.metrics["affected_records"] == 2 and len(r.evidence) == 2


def test_duplicate_customer_id_fails():
    target = customers([("1", "a@x.com", "active"), ("1", "a@x.com", "active"), ("1", "a@x.com", "active"),
                        ("2", "b@x.com", "active")])
    r = check_duplicate_customer_id(CLEAN, target)
    assert r.status == "FAILED"
    assert r.metrics == {"affected_records": 3, "duplicate_ids": 1, "extra_rows": 2}
    assert r.evidence == ["customer_id 1 appears 3 times in target"]


def test_missing_target_ids_fails():
    r = check_missing_target_ids(CLEAN, CLEAN.iloc[[0]])
    assert r.status == "FAILED" and r.metrics["affected_records"] == 2
    assert r.evidence[0].startswith("customer_id 2 ")


def test_invalid_email_fails_and_notes_source_origin():
    target = customers([("1", "a@x.com", "active"), ("2", "broken@", "active")])
    r = check_invalid_email(CLEAN, target)
    assert r.status == "FAILED" and r.metrics["affected_records"] == 1
    assert "'broken@'" in r.evidence[0] and "same value in source" not in r.evidence[0]


def test_invalid_status_fails_case_sensitive_and_null():
    target = customers([("1", "a@x.com", "Active"), ("2", "b@x.com", None), ("3", "c@x.com", "active")])
    r = check_invalid_status(CLEAN, target)
    assert r.status == "FAILED" and r.metrics["affected_records"] == 2
    assert r.metrics["invalid_values"] == {"<null>": 1, "Active": 1}


def test_evidence_is_capped():
    target = customers([(str(i), f"bad{i}", "active") for i in range(MAX_EVIDENCE + 7)])
    r = check_invalid_email(target, target)
    assert r.metrics["affected_records"] == MAX_EVIDENCE + 7
    assert len(r.evidence) == MAX_EVIDENCE + 1 and r.evidence[-1] == "... and 7 more"


# --- the complete suite ---------------------------------------------------------------------

def test_suite_on_clean_data_passes():
    s = run_validation_suite(CLEAN, CLEAN.copy())
    assert s["overall_status"] == "PASSED" and s["total_checks"] == 6 and s["failed_checks"] == 0


def test_suite_counts_are_consistent():
    s = run_validation_suite(CLEAN, CLEAN.iloc[:2])  # only count + missing ids fail
    assert s["overall_status"] == "FAILED"
    assert (s["passed_checks"], s["failed_checks"]) == (4, 2)
    assert s["passed_checks"] + s["failed_checks"] == s["total_checks"] == len(s["results"])
    assert [r["name"] for r in s["results"]] == [
        "record_count", "null_customer_id", "duplicate_customer_id",
        "missing_target_customer_ids", "invalid_email", "invalid_customer_status"]


def test_demo_scenario_produces_expected_failures():
    """Numbers are derived independently from the data files, not hardcoded."""
    source, target, _ = load_scenario()
    s = run_demo_validation_suite()
    by = {r["name"]: r for r in s["results"]}
    assert s["overall_status"] == "FAILED" and s["failed_checks"] == 6

    assert by["record_count"]["metrics"]["target_records"] == len(target)
    assert by["null_customer_id"]["metrics"]["affected_records"] == int(target["customer_id"].isna().sum())
    ids = target["customer_id"].dropna()
    assert by["duplicate_customer_id"]["metrics"]["duplicate_ids"] == int((ids.value_counts() > 1).sum())
    assert by["missing_target_customer_ids"]["metrics"]["affected_records"] == int((~source["customer_id"].isin(ids)).sum())
    assert by["invalid_customer_status"]["metrics"]["affected_records"] == int(
        (~target["status"].isin(["active", "inactive", "churned"])).sum())
    # Evidence points at the actual injected defects.
    assert any("country=SG" in e for e in by["missing_target_customer_ids"]["evidence"])
    assert any("'load'" in e for e in by["record_count"]["evidence"])


def test_demo_data_files_match_generator():
    """The committed CSVs are exactly what the deterministic generator produces."""
    source, target, _ = load_scenario()
    gen_target, _ = simulate_pipeline(build_source())
    assert len(source) == len(build_source()) and len(target) == len(gen_target)
    assert list(target.columns) == list(gen_target.columns)


def test_suite_is_deterministic():
    runs = [json.dumps(run_demo_validation_suite(), sort_keys=True) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


# --- API ------------------------------------------------------------------------------------

client = TestClient(app)


@pytest.fixture
def llm_forbidden(monkeypatch):
    """Fail loudly if anything tries to reach the LLM."""
    def boom(*a, **k):
        raise AssertionError("LLM must not be called")
    monkeypatch.setattr("src.api.main.get_provider", boom)
    monkeypatch.setattr("src.investigation.service.get_provider", boom)
    app.dependency_overrides[get_llm_provider] = lambda: boom
    yield
    app.dependency_overrides.clear()


def test_demo_scenario_endpoint(llm_forbidden):
    r = client.get("/api/demo/scenario")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"pipeline_name", "pipeline_description", "status", "execution_summary",
                         "validation_summary", "validation_results"}
    assert body["status"] == "FAILED"
    assert body["validation_summary"]["total_checks"] == len(body["validation_results"]) == 6
    assert body["validation_results"] == run_demo_validation_suite()["results"]
    source, target, run = load_scenario()
    assert body["execution_summary"]["source_records"] == len(source)
    assert body["execution_summary"]["target_records"] == len(target)
    assert body["execution_summary"]["reported_run_status"] == run["status"]
    for res in body["validation_results"]:
        assert set(res) == RESULT_KEYS


def test_demo_scenario_endpoint_is_deterministic(llm_forbidden):
    assert client.get("/api/demo/scenario").json() == client.get("/api/demo/scenario").json()


def test_demo_results_can_be_posted_to_investigate():
    """UI flow: GET scenario, then POST its results unchanged to /api/investigate."""
    prompts = []

    class Stub:
        def complete(self, system, user):
            prompts.append(user)
            return json.dumps({"summary": "s", "hypotheses": [], "evidence": [], "root_cause": "r",
                               "recommended_fix": "f", "regression_test": "t"})

    app.dependency_overrides[get_llm_provider] = lambda: (lambda: Stub())
    try:
        demo = client.get("/api/demo/scenario").json()
        req = {k: demo[k] for k in ("pipeline_name", "pipeline_description", "execution_summary",
                                     "validation_results")}
        r = client.post("/api/investigate", json=req)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    ctx = json.loads(prompts[0].split("\n\n", 1)[1])
    sent = {v["name"]: v for v in ctx["validation_results"]}
    assert sent["duplicate_customer_id"]["evidence"] == demo["validation_results"][2]["evidence"]
    assert sent["duplicate_customer_id"]["metrics"]["duplicate_ids"] > 0


# --- single source of truth: both demo paths carry identical validation evidence --------------

class RecordingStub:
    """Test-only LLM stand-in: captures the prompt, returns a minimal schema-shaped reply."""

    def __init__(self):
        self.prompts = []

    def complete(self, system, user):
        self.prompts.append(user)
        return json.dumps({"summary": "s", "hypotheses": [], "evidence": [], "root_cause": "r",
                           "recommended_fix": "f", "regression_test": "t"})


def _investigate_ctx(req):
    stub = RecordingStub()
    app.dependency_overrides[get_llm_provider] = lambda: (lambda: stub)
    try:
        r = client.post("/api/investigate", json=req)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    return json.loads(stub.prompts[0].split("\n\n", 1)[1])


DEMO_REQ = {"pipeline_name": "p", "pipeline_description": "d", "use_demo_data": True}


def test_use_demo_data_sends_same_results_as_demo_scenario_endpoint():
    scenario = client.get("/api/demo/scenario").json()
    ctx = _investigate_ctx(DEMO_REQ)
    assert ctx["validation_results"] == scenario["validation_results"]  # same checks, metrics, evidence
    assert len(ctx["validation_results"]) == 6
    _, _, run = load_scenario()
    assert ctx["execution_evidence"]["pipeline_run"] == run  # run log included


def test_use_demo_data_does_not_duplicate_posted_suite_results():
    """UI posts the scenario's results AND sets use_demo_data: each check appears once, from the suite."""
    scenario = client.get("/api/demo/scenario").json()
    tampered = [{**r, "evidence": ["client-supplied"]} for r in scenario["validation_results"]]
    extra = {"name": "custom_check", "status": "FAILED", "details": "kept"}
    ctx = _investigate_ctx({**DEMO_REQ, "validation_results": tampered + [extra]})
    names = [v["name"] for v in ctx["validation_results"]]
    assert names.count("duplicate_customer_id") == 1 and "custom_check" in names
    assert [v for v in ctx["validation_results"] if v["name"] != "custom_check"] == scenario["validation_results"]


def test_all_demo_paths_call_the_one_suite(monkeypatch):
    """Service-level: use_demo_data and investigate_scenario both go through run_demo_validation_suite."""
    from src.investigation import service
    calls = []
    real = service.run_demo_validation_suite
    monkeypatch.setattr(service, "run_demo_validation_suite", lambda: calls.append(1) or real())
    service.investigate_pipeline("p", "d", {}, [], use_demo_data=True, provider=RecordingStub())
    service.investigate_scenario(provider=RecordingStub())
    assert len(calls) == 2
