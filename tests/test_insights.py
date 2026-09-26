"""AI evidence beyond validation, verified row fixes, the suggested CSV and the generated regression test (v2.2).

The LLM is replaced only at the provider boundary (tests/llm_stub.py).
"""

import csv
import io
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_llm_provider, get_run_store, get_target_db
from src.config import DATA_DIR
from src.runs import insights, regression
from src.runs.ingest import parse_csv
from src.runs.service import RUN_SYSTEM_PROMPT
from src.runs.store import RunStore
from src.target.database import initialize_database
from tests.llm_stub import StubProvider, valid_llm_output

client = TestClient(app)
DEMO = DATA_DIR / "demo_uploads"
BAD, FIXED = (DEMO / "customer_bad.csv").read_bytes(), (DEMO / "customer_fixed.csv").read_bytes()

FIXES = [
    {"row": 7, "column": "customer_id", "action": "REPLACE", "current_value": "CUST-1016", "suggested_value": "1016",
     "reason": "strip the prefix", "confidence": "HIGH", "evidence": "[validation.data_type_compatibility.001]"},
    {"row": 8, "column": "status", "action": "REPLACE", "current_value": "active", "suggested_value": "ACTIVE",
     "reason": "upper-case", "confidence": "HIGH", "evidence": "[validation.check_constraints.002]"},
    {"row": 5, "column": "customer_id", "action": "REPLACE", "current_value": "1013", "suggested_value": "1014",
     "reason": "gap in the sequence", "confidence": "MEDIUM", "evidence": "[validation.primary_key_uniqueness.001]"},
    {"row": 3, "column": "name", "action": "NEEDS_DECISION", "current_value": "", "suggested_value": None,
     "reason": "name unknown", "confidence": "LOW", "evidence": "[validation.not_null.001]"},
]
GROUPS = [{"title": "Source formatting", "category": "SOURCE_FORMAT", "explanation": "prefixed IDs, lower-case status",
           "checks": ["data_type_compatibility", "check_constraints"], "rows": [7, 8],
           "evidence": ["[dataset.column_profiles] CUST-1016 among integers"]}]


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


def upload(data, name="customer_bad.csv"):
    return client.post("/api/runs", data={"target_id": "customer"}, files={"file": (name, data, "text/csv")}).json()


def schema():
    return client.get("/api/targets/customer").json()


# --- evidence ---------------------------------------------------------------------------------

def test_column_profiles_show_patterns_validation_does_not():
    up = parse_csv(BAD)
    profiles = {p["column"]: p for p in insights.column_profiles(up, schema())}
    cid = profiles["customer_id"]
    assert cid["usual_shape"] == "integer"
    assert cid["values_not_in_usual_shape"] == [{"row": 7, "value": "CUST-1016", "shape": "letters+number"}]
    assert cid["integer_range"] == {"min": 1011, "max": 1017, "missing_in_range": [1014, 1016]}
    assert profiles["status"]["case_only_mismatches"] == {"active": "ACTIVE"}
    assert profiles["name"]["empty"] == 1
    # Names, e-mails and keys are never listed as value counts.
    assert not any("value_counts" in profiles[c] for c in ("name", "email", "customer_id"))


def test_run_context_has_new_evidence_but_only_failing_rows_in_full():
    llm = use_llm(StubProvider())
    run = upload(BAD)
    assert client.post(f"/api/runs/{run['run_id']}/investigate").status_code == 200
    ctx, prompt = llm.context(), llm.prompts[0]
    ids = {e["id"] for e in ctx["available_evidence"]}
    assert {"dataset.column_profiles", "dataset.failing_rows", "dataset.target_data"} <= ids
    assert "pipeline.run_history" not in ids  # not a retry
    assert [r["row"] for r in ctx["failing_rows"]["rows"]] == [3, 4, 5, 6, 7, 8]
    assert "Kevin Wong" not in prompt  # row 2 passed every check: it is only profiled
    assert ctx["target_data"]["row_count"] == 10
    assert ctx["target_data"]["columns"]["status"]["value_counts"] == {"ACTIVE": 8, "INACTIVE": 1, "CHURNED": 1}
    assert llm.systems[0] == RUN_SYSTEM_PROMPT


def test_run_history_is_the_retry_chain_only():
    llm = use_llm(StubProvider())
    unrelated = upload(BAD, "other.csv")
    first = upload(BAD)
    second = client.post(f"/api/runs/{first['run_id']}/retry",
                         files={"file": ("again.csv", BAD, "text/csv")}).json()
    assert client.post(f"/api/runs/{second['run_id']}/investigate").status_code == 200
    history = llm.context()["run_history"]
    assert [h["run_id"] for h in history] == [first["run_id"]]
    assert "primary_key_uniqueness" in history[0]["failed_checks"]
    assert unrelated["run_id"] not in llm.prompts[0]


# --- row fixes and the suggested CSV ----------------------------------------------------------

def test_row_fixes_are_checked_against_the_file():
    fixes = FIXES + [
        {**FIXES[0], "row": 99},  # no such row
        {**FIXES[0], "column": "nope"},  # no such column
        {**FIXES[1], "current_value": "Active"},  # misquoted
        {**FIXES[1], "row": 2, "suggested_value": "ACTIVE"},  # already has that value
        {**FIXES[1], "suggested_value": "Active"},  # not an allowed value
    ]
    checked, warnings = insights.verify_row_fixes(fixes, parse_csv(BAD), schema())
    assert len(checked) == 6 and len(warnings) == 5  # row 2 is misquoted too
    assert [f["satisfies_constraints"] for f in checked] == [True, True, True, False, True, False]
    assert checked[4]["current_value"] == "active"  # the file's value, not the quoted one
    assert any("row 99" in w for w in warnings) and any("'nope'" in w for w in warnings)


def test_apply_row_fixes_keeps_header_order_and_undecided_values():
    up = parse_csv(BAD)
    fixes, _ = insights.verify_row_fixes(FIXES + [{"row": 4, "column": None, "action": "DELETE_ROW",
                                                  "reason": "dup", "confidence": "LOW"}], up, schema())
    rows = list(csv.reader(io.StringIO(insights.apply_row_fixes(up, fixes))))
    assert rows[0] == up.columns
    ids = [r[0] for r in rows[1:]]
    assert ids == ["1011", "1012", "1014", "1015", "1016", "1017"]  # row 4 deleted, 5 renumbered, 7 unprefixed
    assert rows[2][1] == ""  # NEEDS_DECISION: left as uploaded
    assert rows[-1][-1] == "ACTIVE"


def test_investigate_returns_verified_fixes_and_the_suggested_csv_retries(db):
    use_llm(StubProvider(valid_llm_output(row_fixes=FIXES + [{**FIXES[0], "row": 99}], cause_groups=GROUPS,
                                          prevention=["Export IDs as plain integers"])))
    run = upload(BAD)
    assert client.get(f"/api/runs/{run['run_id']}/suggested-csv").json()["detail"]["code"] == "no_investigation"
    body = client.post(f"/api/runs/{run['run_id']}/investigate").json()
    assert [f["row"] for f in body["row_fixes"]] == [7, 8, 5, 3]
    assert body["row_fixes"][3]["suggested_value"] is None and body["row_fixes"][0]["satisfies_constraints"]
    assert body["cause_groups"][0]["category"] == "SOURCE_FORMAT" and body["prevention"]
    assert any("row 99" in w for w in body["evidence_warnings"])
    assert body["regression_test"].startswith('"""Data check for table `customer`')
    assert any(s["stage"] == "regression_test_generation" and "deterministic" in s["description"]
               for s in body["investigation_trace"])
    assert client.get(f"/api/runs/{run['run_id']}").json()["investigation"] == body

    r = client.get(f"/api/runs/{run['run_id']}/suggested-csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["x-fixes-applied"] == "3"
    assert 'filename="customer_bad_suggested.csv"' in r.headers["content-disposition"]
    retried = client.post(f"/api/runs/{run['run_id']}/retry",
                          files={"file": ("customer_bad_suggested.csv", r.content, "text/csv")}).json()
    failed = {v["name"] for v in retried["validation_results"] if v["status"] == "FAILED"}
    # Fixed by the suggestions: type, duplicate key, case. Left for the user: the empty name, PENDING, the e-mail.
    assert failed == {"not_null", "unique_constraints", "check_constraints"}


def test_suggested_csv_needs_an_applicable_fix():
    use_llm(StubProvider(valid_llm_output(row_fixes=[FIXES[3]])))
    run = upload(BAD)
    client.post(f"/api/runs/{run['run_id']}/investigate")
    r = client.get(f"/api/runs/{run['run_id']}/suggested-csv")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_suggested_fixes"
    assert client.get("/api/runs/run_nope/suggested-csv").status_code == 404


def test_output_without_the_new_fields_still_works():
    use_llm(StubProvider(valid_llm_output()))
    run = upload(BAD)
    body = client.post(f"/api/runs/{run['run_id']}/investigate").json()
    assert body["row_fixes"] == [] and body["cause_groups"] == [] and body["prevention"] == []


def test_invalid_row_fix_action_is_rejected_then_retried():
    llm = use_llm(StubProvider(valid_llm_output(row_fixes=[{**FIXES[0], "action": "GUESS"}]),
                               valid_llm_output(row_fixes=FIXES)))
    run = upload(BAD)
    r = client.post(f"/api/runs/{run['run_id']}/investigate")
    assert r.status_code == 200 and len(llm.prompts) == 2 and len(r.json()["row_fixes"]) == 4


# --- regression test --------------------------------------------------------------------------

def test_generated_regression_test_runs(tmp_path):
    use_llm(StubProvider())
    run = upload(BAD)
    code = client.post(f"/api/runs/{run['run_id']}/investigate").json()["regression_test"]
    test = tmp_path / "test_customer_data.py"
    test.write_text(code)

    def pytest_run(csv_path=None):
        env = {**os.environ, **({"CSV_PATH": str(csv_path)} if csv_path else {})}
        env.pop("CSV_PATH", None) if not csv_path else None
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test)],
                              cwd=tmp_path, env=env, capture_output=True, text=True)

    assert "1 passed, 1 skipped" in pytest_run().stdout
    assert "2 passed" in pytest_run(DEMO / "customer_fixed.csv").stdout
    assert "1 failed, 1 passed" in pytest_run(DEMO / "customer_bad.csv").stdout


def test_generated_regression_test_catches_the_runs_failures():
    up = parse_csv(BAD)
    s = schema()
    s["columns_with_default"] = []
    from src.runs.validation import validate_upload
    results = validate_upload(s, up)
    _, code = regression.generate(s, up, results, "customer", "crm.db", "run_x")
    failed = sorted(v["name"] for v in results if v["status"] == "FAILED")
    assert f"assert found == {failed!r}" in code
