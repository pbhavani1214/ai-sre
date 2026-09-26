"""Proves the deterministic validation tools work, on small fixtures and on the demo scenario."""

import json

import pandas as pd
import pytest

from src.data.scenario import load_scenario
from src.investigation.models import InvestigationParseError
from src.investigation.service import investigate_scenario, parse_llm_json
from tests.llm_stub import valid_llm_output
from src.validation.tools import (
    duplicate_customer_id_check,
    invalid_email_check,
    missing_target_records,
    null_customer_id_check,
    record_count_comparison,
    run_all_validations,
)


def df(ids, emails=None):
    emails = emails or [f"u{i}@example.com" for i in range(len(ids))]
    return pd.DataFrame({"customer_id": ids, "email": emails})


# --- unit tests on tiny fixtures ---------------------------------------------

def test_record_count_pass_and_fail():
    assert record_count_comparison(df(["1", "2"]), df(["1", "2"])).passed
    r = record_count_comparison(df(["1", "2"]), df(["1"]))
    assert not r.passed and r.details["difference"] == -1


def test_null_customer_id():
    assert null_customer_id_check(df(["1", "2"])).passed
    r = null_customer_id_check(df(["1", None, "  "]))
    assert not r.passed and r.details["null_count"] == 2


def test_duplicate_customer_id():
    assert duplicate_customer_id_check(df(["1", "2"])).passed
    r = duplicate_customer_id_check(df(["1", "2", "2", "2", None, None]))
    assert r.details["duplicates"] == {"2": 3} and r.details["extra_rows"] == 2  # nulls not dupes


def test_missing_target_records():
    assert missing_target_records(df(["1", "2"]), df(["2", "1"])).passed
    r = missing_target_records(df(["1", "2", "3"]), df(["1"]))
    assert [m["customer_id"] for m in r.details["missing_records"]] == ["2", "3"]


def test_invalid_email():
    good = ["a@b.com", "x.y+z@sub.example.org"]
    bad = ["no-at-sign.com", "a@b", "a b@c.com", None, ""]
    assert invalid_email_check(df(["1", "2"], good)).passed
    r = invalid_email_check(df([str(i) for i in range(len(bad))], bad))
    assert r.details["invalid_count"] == len(bad)


# --- the demo scenario produces the expected deterministic evidence ----------

def test_scenario_validations_are_deterministic():
    source, target, _ = load_scenario()
    results = {r.check: r for r in run_all_validations(source, target)}

    assert results["record_count_comparison"].details == {"source_count": 20, "target_count": 23, "difference": 3}
    assert results["null_customer_id_check"].details["null_count"] == 1
    assert results["duplicate_customer_id_check"].details["duplicates"] == {
        "1012": 2, "1013": 2, "1015": 2, "1016": 2, "1017": 2}
    missing = {m["customer_id"] for m in results["missing_target_records"].details["missing_records"]}
    assert missing == {"1004", "1014", "CUST-1020"}
    assert results["invalid_email_check[source]"].details["invalid_count"] == 1
    assert results["invalid_email_check[target]"].details["invalid_count"] == 1

    # Running twice gives identical output.
    again = [r.to_dict() for r in run_all_validations(source, target)]
    assert again == [r.to_dict() for r in results.values()]


# --- investigation plumbing (LLM stubbed; checks wiring, not conclusions) -----

class RecordingProvider:
    """Test double: records the prompt and returns a schema-shaped echo."""

    def __init__(self):
        self.user_prompt = None

    def complete(self, system, user):
        self.user_prompt = user
        return "```json\n" + json.dumps(valid_llm_output()) + "\n```"  # fenced, as models often reply


def test_investigation_sends_all_evidence_and_parses_result():
    provider = RecordingProvider()
    result = investigate_scenario(provider=provider)

    ctx = json.loads(provider.user_prompt.split("\n\n", 1)[1])
    assert set(ctx) == {"pipeline_name", "pipeline_description", "source", "target", "validation_results",
                        "execution_evidence", "validation_summary", "available_evidence"}
    assert len(ctx["validation_results"]) == 6
    assert "logs" in ctx["execution_evidence"]["pipeline_run"]

    assert result.hypotheses[0].status == "SUPPORTED"
    assert result.observed_facts == valid_llm_output()["observed_facts"]
    assert result.regression_test.code.startswith("def test_x")


def test_parse_rejects_non_json():
    with pytest.raises(InvestigationParseError):
        parse_llm_json("I could not determine the cause.")
