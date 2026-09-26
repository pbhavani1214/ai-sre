"""Deterministic validation suite: runs the checks in tools.py and reports them in one
structured, UI/LLM-friendly format. Every number and evidence line is derived from the data
(or the pipeline run record); evidence is capped per check to keep LLM prompts small.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from src.data.scenario import PIPELINE_DESCRIPTION, PIPELINE_NAME, VALID_STATUSES, load_scenario
from src.validation import tools

MAX_EVIDENCE = 5

# Severity is a fixed property of each check (how bad a failure is), not of the result.
SEVERITY = {
    "record_count": "HIGH",
    "null_customer_id": "HIGH",
    "duplicate_customer_id": "HIGH",
    "missing_target_customer_ids": "HIGH",
    "invalid_email": "MEDIUM",
    "invalid_customer_status": "MEDIUM",
}


@dataclass
class CheckResult:
    name: str
    status: str  # "PASSED" | "FAILED"
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result(name: str, passed: bool, summary: str, metrics: dict, evidence: list[str], total: int) -> CheckResult:
    evidence = evidence[:MAX_EVIDENCE]
    if total > len(evidence):
        evidence.append(f"... and {total - len(evidence)} more")
    return CheckResult(name, "PASSED" if passed else "FAILED", SEVERITY[name], summary, metrics, evidence)


def _id_set(df: pd.DataFrame) -> set[str]:
    return set(tools._ids(df["customer_id"]).dropna())


def check_record_count(source: pd.DataFrame, target: pd.DataFrame, run: dict | None = None) -> CheckResult:
    r = tools.record_count_comparison(source, target)
    d = r.details
    evidence = [] if r.passed else [f"source has {d['source_count']} rows, target has {d['target_count']} rows"]
    if not r.passed and run:  # row flow per pipeline step, from the execution record
        for step in run.get("steps", []):
            rows_out = step.get("rows_out", step.get("rows_written"))
            if step.get("rows_in") is not None and rows_out is not None and rows_out != step["rows_in"]:
                evidence.append(f"pipeline step '{step['name']}': {step['rows_in']} rows in, {rows_out} rows out")
    return _result(
        "record_count", r.passed,
        "Source and target record counts match" if r.passed else
        f"Target has {abs(d['difference'])} {'more' if d['difference'] > 0 else 'fewer'} records than source",
        {"source_records": d["source_count"], "target_records": d["target_count"],
         "difference": d["difference"], "affected_records": abs(d["difference"])},
        evidence, len(evidence),
    )


def check_null_customer_id(source: pd.DataFrame, target: pd.DataFrame) -> CheckResult:
    r = tools.null_customer_id_check(target)
    n = r.details["null_count"]
    evidence = [f"target row with name '{row.get('name')}' has a null customer_id" for row in r.details["rows"]]
    return _result(
        "null_customer_id", r.passed,
        "No null customer IDs in target" if r.passed else f"{n} target record(s) have a null customer_id",
        {"affected_records": n}, evidence, n,
    )


def check_duplicate_customer_id(source: pd.DataFrame, target: pd.DataFrame) -> CheckResult:
    r = tools.duplicate_customer_id_check(target)
    dupes = r.details["duplicates"]
    evidence = [f"customer_id {cid} appears {count} times in target" for cid, count in dupes.items()]
    return _result(
        "duplicate_customer_id", r.passed,
        "No duplicate customer IDs in target" if r.passed else
        f"{len(dupes)} customer ID(s) duplicated in target ({r.details['extra_rows']} extra row(s))",
        {"affected_records": sum(dupes.values()), "duplicate_ids": len(dupes), "extra_rows": r.details["extra_rows"]},
        evidence, len(dupes),
    )


def check_missing_target_ids(source: pd.DataFrame, target: pd.DataFrame) -> CheckResult:
    r = tools.missing_target_records(source, target)
    n = r.details["missing_count"]
    evidence = [
        f"customer_id {row['customer_id']} (country={row.get('country')}) is in source but not in target"
        for row in r.details["missing_records"]
    ]
    return _result(
        "missing_target_customer_ids", r.passed,
        "Every source customer ID is present in target" if r.passed else
        f"{n} source customer ID(s) missing from target",
        {"affected_records": n}, evidence, n,
    )


def check_invalid_email(source: pd.DataFrame, target: pd.DataFrame) -> CheckResult:
    r = tools.invalid_email_check(target, label="target")
    n = r.details["invalid_count"]
    source_emails = set(source["email"].astype("string").str.lower().dropna())
    evidence = [
        f"customer_id {row.get('customer_id')} has invalid email '{row.get('email')}'"
        + (" (same value in source)" if str(row.get("email")).lower() in source_emails else "")
        for row in r.details["rows"]
    ]
    return _result(
        "invalid_email", r.passed,
        "All target emails are valid" if r.passed else f"{n} target record(s) have an invalid email",
        {"affected_records": n}, evidence, n,
    )


def check_invalid_status(source: pd.DataFrame, target: pd.DataFrame) -> CheckResult:
    r = tools.invalid_status_check(target, VALID_STATUSES, label="target")
    n = r.details["invalid_count"]
    source_ids = {str(i): s for i, s in zip(tools._ids(source["customer_id"]), source["status"])}
    evidence = []
    for row in r.details["rows"]:
        cid = row.get("customer_id")
        line = f"customer_id {cid} has status '{row.get('status')}' (allowed: {', '.join(VALID_STATUSES)})"
        if str(cid) in source_ids and source_ids[str(cid)] == row.get("status"):
            line += " (same value in source)"
        evidence.append(line)
    return _result(
        "invalid_customer_status", r.passed,
        "All target status values are valid" if r.passed else
        f"{n} target record(s) have an invalid status",
        {"affected_records": n, "invalid_values": r.details["invalid_values"]}, evidence, n,
    )


CHECKS = [
    check_null_customer_id,
    check_duplicate_customer_id,
    check_missing_target_ids,
    check_invalid_email,
    check_invalid_status,
]


def run_validation_suite(source: pd.DataFrame, target: pd.DataFrame, run: dict | None = None) -> dict[str, Any]:
    results = [check_record_count(source, target, run)] + [check(source, target) for check in CHECKS]
    passed = sum(r.status == "PASSED" for r in results)
    return {
        "overall_status": "PASSED" if passed == len(results) else "FAILED",
        "total_checks": len(results),
        "passed_checks": passed,
        "failed_checks": len(results) - passed,
        "results": [r.to_dict() for r in results],
    }


def run_demo_validation_suite() -> dict[str, Any]:
    """Run the suite against the bundled synthetic scenario (no LLM)."""
    source, target, run = load_scenario()
    return run_validation_suite(source, target, run)


def get_demo_scenario() -> dict[str, Any]:
    """Complete deterministic demo state for the UI, before any AI investigation."""
    source, target, run = load_scenario()
    suite = run_validation_suite(source, target, run)
    return {
        "pipeline_name": PIPELINE_NAME,
        "pipeline_description": PIPELINE_DESCRIPTION,
        "status": suite["overall_status"],
        "execution_summary": {
            "source_records": len(source),
            "target_records": len(target),
            "run_id": run.get("run_id"),
            "reported_run_status": run.get("status"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
        },
        "validation_summary": {k: suite[k] for k in ("total_checks", "passed_checks", "failed_checks")},
        "validation_results": suite["results"],
    }
