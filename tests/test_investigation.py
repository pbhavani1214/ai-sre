"""Evidence-driven investigation workflow tests.

Only the LLM boundary is replaced (tests/llm_stub.py). The deterministic validation suite,
scenario data, prompt building, parsing, citation checks and trace all run for real.
"""

import json
import socket
import urllib.error

import pytest
from fastapi.testclient import TestClient

from src.ai import provider as provider_mod
from src.ai.provider import AnthropicProvider, LLMError, LLMTimeoutError
from src.api.main import app, get_llm_provider
from src.investigation.service import SYSTEM_PROMPT, investigate_pipeline
from src.validation.suite import run_demo_validation_suite
from tests.llm_stub import FailingProvider, StubProvider, valid_llm_output

client = TestClient(app)

REQ = {
    "pipeline_name": "Customer Data Pipeline",
    "pipeline_description": "Load customer records from source to target",
    "execution_summary": {"source_records": 1000, "target_records": 970},
    "validation_results": [
        {"name": "duplicate_customer_id", "status": "FAILED", "details": "20 duplicate customer IDs detected"}
    ],
}
DEMO_REQ = {"pipeline_name": "Customer Nightly Sync", "pipeline_description": "demo", "use_demo_data": True}

TRACE_STAGES = ["evidence_collection", "validation_analysis", "hypothesis_generation", "evidence_correlation",
                "root_cause_analysis", "remediation_generation", "regression_test_generation"]


def post(provider, req=REQ):
    app.dependency_overrides[get_llm_provider] = lambda: (lambda: provider)
    try:
        return client.post("/api/investigate", json=req)
    finally:
        app.dependency_overrides.clear()


# 1-9: structured response -------------------------------------------------------------------

def test_valid_structured_response():
    r = post(StubProvider())
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "summary", "observed_facts", "hypotheses", "root_cause_status", "root_cause", "root_cause_evidence",
        "root_cause_reasoning", "evidence", "recommended_fix", "regression_test", "investigation_trace",
        "evidence_warnings"}
    assert body["summary"] == "stub summary" and body["root_cause_status"] == "IDENTIFIED"
    assert body["regression_test"].startswith("# test_x: desc\n") and "def test_x" in body["regression_test"]


def test_multiple_hypotheses_preserved_in_order():
    body = post(StubProvider()).json()
    assert [h["hypothesis"] for h in body["hypotheses"]] == ["h1", "h2", "h3"]
    assert all(set(h) == {"hypothesis", "status", "evidence", "reasoning"} for h in body["hypotheses"])
    assert [h["reasoning"] for h in body["hypotheses"]] == ["r1", "r2", "r3"]


@pytest.mark.parametrize("status", ["SUPPORTED", "REJECTED", "INCONCLUSIVE"])
def test_each_hypothesis_status(status):
    out = valid_llm_output()
    out["hypotheses"][0]["status"] = status
    body = post(StubProvider(out)).json()
    assert body["hypotheses"][0]["status"] == status


def test_hypothesis_status_is_case_normalised():
    out = valid_llm_output()
    out["hypotheses"][0]["status"] = "supported"
    assert post(StubProvider(out)).json()["hypotheses"][0]["status"] == "SUPPORTED"


def test_statuses_are_not_forced_to_a_mix():
    out = valid_llm_output()
    for h in out["hypotheses"]:
        h["status"] = "INCONCLUSIVE"
    out.update(root_cause_status="INCONCLUSIVE", root_cause="Insufficient evidence", root_cause_evidence=[])
    body = post(StubProvider(out)).json()
    assert {h["status"] for h in body["hypotheses"]} == {"INCONCLUSIVE"}
    assert body["root_cause_status"] == "INCONCLUSIVE"
    assert not any("IDENTIFIED" in w for w in body["evidence_warnings"])  # inconclusive is a valid outcome


def test_observed_facts_parsing():
    facts = ["[validation.duplicate_customer_id] 20 duplicate customer IDs detected",
             "[pipeline.execution_summary] source_records=1000, target_records=970"]
    body = post(StubProvider(valid_llm_output(observed_facts=facts))).json()
    assert body["observed_facts"] == facts
    assert body["evidence"] == facts  # backward-compatible alias


def test_root_cause_evidence_parsing():
    ev = ["[validation.duplicate_customer_id] 20 duplicate customer IDs detected"]
    body = post(StubProvider(valid_llm_output(root_cause_evidence=ev))).json()
    assert body["root_cause_evidence"] == ev


def test_root_cause_reasoning_parsing():
    body = post(StubProvider(valid_llm_output(root_cause_reasoning="Because X correlates with Y."))).json()
    assert body["root_cause_reasoning"] == "Because X correlates with Y."


def test_investigation_trace_reflects_real_stages_and_evidence():
    body = post(StubProvider(), DEMO_REQ).json()
    trace = body["investigation_trace"]
    assert [t["stage"] for t in trace] == TRACE_STAGES
    by = {t["stage"]: t["description"] for t in trace}
    suite = run_demo_validation_suite()
    assert f"{suite['failed_checks']} of {suite['total_checks']}" in by["validation_analysis"]
    assert "status=SUCCESS" in by["validation_analysis"]  # from the real run record
    assert "validation.record_count" in by["evidence_collection"] and "pipeline.run_log" in by["evidence_collection"]
    assert "StubProvider" in by["hypothesis_generation"] and "3 hypotheses" in by["hypothesis_generation"]
    assert "1 SUPPORTED, 1 REJECTED, 1 INCONCLUSIVE" in by["evidence_correlation"]
    assert "not been applied" in by["remediation_generation"]
    assert "not been executed" in by["regression_test_generation"]


# 10-13: failure handling ----------------------------------------------------------------------

def test_malformed_json_is_retried_once_then_502():
    stub = StubProvider("{not valid json")
    r = post(stub)
    assert r.status_code == 502 and "invalid investigation" in r.json()["detail"]
    assert len(stub.prompts) == 2
    assert "REJECTED BY THE SCHEMA VALIDATOR" in stub.systems[1]
    assert "Traceback" not in r.text


def test_retry_recovers_and_is_recorded_in_trace():
    stub = StubProvider("garbage", valid_llm_output())
    r = post(stub)
    assert r.status_code == 200 and len(stub.prompts) == 2
    gen = {t["stage"]: t["description"] for t in r.json()["investigation_trace"]}["hypothesis_generation"]
    assert "attempt 2" in gen


def test_missing_required_fields_is_502():
    out = valid_llm_output()
    del out["root_cause_reasoning"], out["observed_facts"]
    r = post(StubProvider(out))
    assert r.status_code == 502
    assert "observed_facts" in r.json()["detail"] and "root_cause_reasoning" in r.json()["detail"]


def test_empty_required_string_is_502():
    assert post(StubProvider(valid_llm_output(summary="   "))).status_code == 502


def test_invalid_hypothesis_status_is_502():
    out = valid_llm_output()
    out["hypotheses"][1]["status"] = "PROBABLY"
    r = post(StubProvider(out))
    assert r.status_code == 502 and "hypotheses[1].status" in r.json()["detail"]


def test_empty_hypotheses_is_502():
    assert post(StubProvider(valid_llm_output(hypotheses=[]))).status_code == 502


@pytest.mark.parametrize("reply", ["", "   ", "null", "[]"])
def test_empty_or_non_object_response_is_502(reply):
    assert post(StubProvider(reply)).status_code == 502


@pytest.mark.parametrize("exc, code, text", [
    (LLMError("HTTP 529 overloaded"), 502, "provider unavailable"),
    (LLMTimeoutError("No response within 120s"), 504, "timed out"),
    (RuntimeError("secret internal detail"), 500, "internal error"),
])
def test_provider_failures_map_to_clean_errors(exc, code, text):
    r = post(FailingProvider(exc))
    assert r.status_code == code and text in r.json()["detail"]
    assert "Traceback" not in r.text and "secret internal detail" not in r.text


def test_provider_timeout_is_classified(monkeypatch):
    def slow(*a, **k):
        raise urllib.error.URLError(socket.timeout("timed out"))
    monkeypatch.setattr(provider_mod.urllib.request, "urlopen", slow)
    with pytest.raises(LLMTimeoutError):
        AnthropicProvider(api_key="test", timeout=1).complete("s", "u")


def test_truncated_provider_response_is_an_error(monkeypatch):
    monkeypatch.setattr(provider_mod, "_post_json", lambda *a, **k: {"stop_reason": "max_tokens", "content": []})
    with pytest.raises(LLMError, match="truncated"):
        AnthropicProvider(api_key="test").complete("s", "u")


# 14: evidence preservation and grounding ------------------------------------------------------

def test_supplied_evidence_reaches_llm_verbatim_and_is_catalogued():
    stub = StubProvider()
    post(stub)
    ctx = stub.context()
    assert ctx["validation_results"][0]["details"] == "20 duplicate customer IDs detected"
    assert ctx["execution_evidence"]["execution_summary"] == {"source_records": 1000, "target_records": 970}
    ids = {e["id"] for e in ctx["available_evidence"]}
    assert ids == {"pipeline.execution_summary", "validation.summary", "validation.duplicate_customer_id"}
    assert ctx["validation_summary"]["failed_checks"] == 1


def test_llm_text_is_not_rewritten():
    out = valid_llm_output()
    body = post(StubProvider(out)).json()
    assert body["hypotheses"][0]["evidence"] == out["hypotheses"][0]["evidence"]
    assert body["root_cause"] == out["root_cause"] and body["recommended_fix"] == out["recommended_fix"]


def test_unknown_or_missing_citations_are_flagged_not_hidden():
    out = valid_llm_output(
        observed_facts=["[validation.made_up_check] 999 rows lost", "no citation here"],
        root_cause_evidence=["[validation.duplicate_customer_id] ok"],
    )
    body = post(StubProvider(out)).json()
    assert body["observed_facts"] == out["observed_facts"]  # kept as-is, but flagged
    w = body["evidence_warnings"]
    assert any("validation.made_up_check" in x for x in w)
    assert any("observed_facts[1] cites no evidence ID" in x for x in w)
    assert not any("root_cause_evidence" in x for x in w)


def test_identified_root_cause_without_support_is_flagged():
    out = valid_llm_output()
    for h in out["hypotheses"]:
        h["status"] = "REJECTED"
    body = post(StubProvider(out)).json()
    assert any("no hypothesis is SUPPORTED" in x for x in body["evidence_warnings"])


def test_datasets_are_summarised_not_sent_raw():
    stub = StubProvider()
    post(stub, DEMO_REQ)
    ctx = stub.context()
    for side in ("source", "target"):
        assert set(ctx[side]) == {"row_count", "columns", "null_counts"}
    assert "Alice Carter" not in stub.prompts[0]  # a customer name that only exists in the raw CSV rows


def test_prompt_contains_no_expected_conclusion():
    lowered = SYSTEM_PROMPT.lower()
    for leak in ("singapore", " sg", "retry", "inner join", "region_lookup", "cust-1020", "duplicate"):
        assert leak not in lowered


# 15: demo path still uses the unified six-check suite (NOT mocked) ------------------------------

def test_use_demo_data_sends_unified_suite():
    stub = StubProvider()
    r = post(stub, DEMO_REQ)
    assert r.status_code == 200, r.text
    ctx = stub.context()
    suite = run_demo_validation_suite()
    assert ctx["validation_results"] == suite["results"] and len(suite["results"]) == 6
    assert ctx["validation_summary"]["failed_checks"] == suite["failed_checks"]
    ids = {e["id"] for e in ctx["available_evidence"]}
    assert {f"validation.{r['name']}" for r in suite["results"]} <= ids
    assert {"pipeline.run_log", "pipeline.execution_summary", "validation.summary"} <= ids
    assert ctx["execution_evidence"]["pipeline_run"]["status"] == "SUCCESS"


def test_service_level_demo_investigation():
    result = investigate_pipeline("p", "d", {}, [], use_demo_data=True, provider=StubProvider())
    assert [t.stage for t in result.investigation_trace] == TRACE_STAGES
    assert result.evidence_warnings == []  # stub cites only IDs that exist in the demo evidence
