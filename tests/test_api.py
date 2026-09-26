"""API tests. The LLM is replaced ONLY here, via FastAPI dependency override."""

import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_llm_provider

VALID_REQUEST = {
    "pipeline_name": "Customer Data Pipeline",
    "pipeline_description": "Load customer records from source to target",
    "execution_summary": {"source_records": 1000, "target_records": 970},
    "validation_results": [
        {"name": "duplicate_customer_id", "status": "FAILED", "details": "20 duplicate customer IDs detected"}
    ],
}

STUB_LLM_OUTPUT = {
    "summary": "stub summary",
    "hypotheses": [
        {"statement": "h1", "status": "confirmed", "confidence": 0.9, "supporting_evidence": ["e1"]},
        {"statement": "h2", "status": "rejected", "confidence": 0.1, "contradicting_evidence": ["e2"]},
        {"statement": "h3", "status": "weird-value", "confidence": 0.5},
    ],
    "evidence": [{"source": "validation", "observation": "obs"}],
    "root_cause": "stub root cause",
    "recommended_fix": "stub fix",
    "regression_test": {"name": "test_x", "description": "desc", "code": "def test_x(): pass"},
}


class StubProvider:
    """Test double at the LLM boundary: records prompts, returns a fixed schema-shaped reply."""

    def __init__(self, reply: str = json.dumps(STUB_LLM_OUTPUT)):
        self.reply, self.prompts = reply, []

    def complete(self, system, user):
        self.prompts.append(user)
        return self.reply


@pytest.fixture
def stub():
    provider = StubProvider()
    app.dependency_overrides[get_llm_provider] = lambda: (lambda: provider)
    yield provider
    app.dependency_overrides.clear()


client = TestClient(app)


def test_health(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["llm_configured"] is False


def test_investigate_returns_contract_shape(stub):
    r = client.post("/api/investigate", json=VALID_REQUEST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"summary", "hypotheses", "root_cause", "evidence", "recommended_fix", "regression_test"}
    assert [h["status"] for h in body["hypotheses"]] == ["supported", "rejected", "inconclusive"]
    assert set(body["hypotheses"][0]) == {"hypothesis", "evidence", "status"}
    assert body["evidence"] == ["validation: obs"]
    assert "def test_x" in body["regression_test"]

    # The request's evidence reached the LLM prompt.
    ctx = json.loads(stub.prompts[0].split("\n\n", 1)[1])
    assert ctx["pipeline_name"] == "Customer Data Pipeline"
    assert ctx["execution_evidence"]["execution_summary"] == {"source_records": 1000, "target_records": 970}
    assert ctx["validation_results"][0]["name"] == "duplicate_customer_id"


def test_investigate_with_demo_data_adds_real_validation_evidence(stub):
    req = {**VALID_REQUEST, "validation_results": [], "use_demo_data": True}
    assert client.post("/api/investigate", json=req).status_code == 200
    ctx = json.loads(stub.prompts[0].split("\n\n", 1)[1])
    names = {v.get("name") for v in ctx["validation_results"]}
    assert "duplicate_customer_id" in names and "missing_target_customer_ids" in names
    assert "logs" in ctx["execution_evidence"]["pipeline_run"]


@pytest.mark.parametrize("bad", [
    {},                                                            # empty body
    {**VALID_REQUEST, "pipeline_name": ""},                        # empty name
    {k: v for k, v in VALID_REQUEST.items() if k != "pipeline_description"},
    {**VALID_REQUEST, "execution_summary": {"source_records": "lots"}},
    {**VALID_REQUEST, "validation_results": [{"status": "FAILED"}]},  # missing name
    {**VALID_REQUEST, "validation_results": []},                   # no evidence at all
])
def test_investigate_rejects_invalid_requests(stub, bad):
    r = client.post("/api/investigate", json=bad)
    assert r.status_code == 422
    assert stub.prompts == []  # LLM never called


def test_investigate_non_json_body(stub):
    r = client.post("/api/investigate", content="not json", headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_investigate_bad_llm_output_is_502():
    app.dependency_overrides[get_llm_provider] = lambda: (lambda: StubProvider(reply="no json here"))
    try:
        r = client.post("/api/investigate", json=VALID_REQUEST)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 502


def test_investigate_without_llm_key_is_503(monkeypatch):
    for var in ("LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    r = client.post("/api/investigate", json=VALID_REQUEST)
    assert r.status_code == 503
    assert "LLM not configured" in r.json()["detail"]


def test_invalid_request_is_422_even_without_llm_key(monkeypatch):
    for var in ("LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert client.post("/api/investigate", json={"pipeline_name": ""}).status_code == 422


def test_cors_allows_vite_dev_origin():
    r = client.options("/api/investigate", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
