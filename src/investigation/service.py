"""Investigation service: gathers deterministic evidence and asks the LLM to reason over it.

The deterministic backend establishes WHAT happened (validation suite + pipeline run record).
The LLM is asked, in one structured call, WHY it may have happened and WHAT to do about it.
The service then checks the LLM's evidence citations against the evidence it was actually given
and records the real stages of the workflow as an investigation trace.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from src.ai.provider import LLMProvider, get_provider
from src.data.scenario import PIPELINE_DESCRIPTION, PIPELINE_NAME, load_scenario
from src.investigation.models import (
    HYPOTHESIS_STATUSES,
    REQUIRED_KEYS,
    InvestigationParseError,
    InvestigationResult,
    TraceStep,
)
from src.validation.suite import run_demo_validation_suite
from src.validation.tools import ValidationResult, run_all_validations

MAX_ATTEMPTS = 2  # one retry if the LLM output fails schema validation

SYSTEM_PROMPT = """You are an AI Software Reliability Engineer investigating a data pipeline.

You receive a JSON evidence package. Deterministic code has already established WHAT happened:
validation results (with metrics and sample evidence), a validation summary, dataset summaries,
and the pipeline's execution record (config, per-step row counts, log lines).
Your job is to investigate WHY it may have happened and WHAT should be done.

RULES
1. The supplied evidence is authoritative. Do not contradict it.
2. You may reason about the evidence, correlate items, and draw inferences.
3. Never manufacture evidence: no record counts, IDs, percentages, pipeline stages, errors,
   log lines or validation failures that do not appear in the evidence package.
4. Keep facts and hypotheses separate. observed_facts are restatements of supplied evidence only;
   interpretations belong in hypotheses and reasoning.
5. A pipeline that reports technical success can still produce incorrect data. Treat the
   execution status and the data validation results as independent signals.
6. If the evidence does not reliably establish a root cause, say so: set root_cause_status to
   "INCONCLUSIVE" and describe what additional evidence would be needed. Do not guess.

CITATIONS
Every entry in observed_facts, each hypothesis's evidence, and root_cause_evidence must begin with
one or more evidence IDs in square brackets, taken ONLY from "available_evidence" in the package,
e.g. "[validation.record_count] ...". Quote or closely paraphrase the cited evidence.

METHOD
1. Observed facts: list the key facts from the evidence (bounded; the most relevant items).
2. Hypotheses: propose 2-3 plausible, competing explanations. The evidence may point to more
   than one independent defect.
3. Evaluate each hypothesis against the evidence:
   SUPPORTED    - the evidence meaningfully supports it.
   REJECTED     - the evidence contradicts or substantially weakens it.
   INCONCLUSIVE - there is not enough evidence to decide.
   Assign statuses honestly; there is no required mix, and do not mark a hypothesis SUPPORTED
   just so that a root cause can be reported.
4. Root cause: choose the strongest evidence-supported explanation (it may cover more than one
   defect), or report INCONCLUSIVE.
5. Recommended fix: practical changes that address the evidence-supported failure. It has not
   been applied; do not claim it has.
6. Regression test: a concrete pytest (pandas) test that would detect the same class of failure
   in a future run. Use specific assertions on columns/values/counts that appear in the evidence.

OUTPUT
Respond with ONE JSON object and nothing else:
{
  "summary": "2-4 sentence overview",
  "observed_facts": ["[evidence.id] fact", "..."],
  "hypotheses": [
    {"hypothesis": "string", "status": "SUPPORTED|REJECTED|INCONCLUSIVE",
     "evidence": ["[evidence.id] ...", "..."], "reasoning": "why this status"}
  ],
  "root_cause_status": "IDENTIFIED|INCONCLUSIVE",
  "root_cause": "string",
  "root_cause_evidence": ["[evidence.id] ...", "..."],
  "root_cause_reasoning": "string",
  "recommended_fix": "string",
  "regression_test": {"name": "test_...", "description": "string", "code": "python source"}
}"""

RETRY_NOTE = """

YOUR PREVIOUS RESPONSE WAS REJECTED BY THE SCHEMA VALIDATOR: {error}
Return ONLY a single JSON object that satisfies the OUTPUT schema above."""

_EVIDENCE_REF = re.compile(r"\b(?:validation|pipeline|dataset)\.[A-Za-z0-9_]+(?:\.\d+)?")


# --- evidence context -----------------------------------------------------------------------

def _profile(df: pd.DataFrame) -> dict[str, Any]:
    """Bounded dataset summary: shape and null counts only, never raw rows."""
    return {
        "row_count": len(df),
        "columns": list(df.columns),
        "null_counts": {c: int(n) for c, n in df.isna().sum().items()},
    }


def build_context(
    pipeline_description: str,
    source: pd.DataFrame,
    target: pd.DataFrame,
    validation_results: list[ValidationResult],
    execution_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pipeline_description": pipeline_description,
        "source": _profile(source),
        "target": _profile(target),
        "validation_results": [v.to_dict() for v in validation_results],
        "execution_evidence": execution_evidence,
    }


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(name).lower()).strip("_")


def _is_passed(v: dict[str, Any]) -> bool:
    if "status" in v:
        return str(v["status"]).strip().upper() in ("PASSED", "PASS", "OK")
    return bool(v.get("passed"))


def summarize_validations(results: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [str(v.get("name") or v.get("check")) for v in results if not _is_passed(v)]
    return {
        "overall_status": "FAILED" if failed else "PASSED",
        "total_checks": len(results),
        "passed_checks": len(results) - len(failed),
        "failed_checks": len(failed),
        "failed_check_names": failed,
    }


def _run_record(context: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """The pipeline execution record and where it lives in the context (API vs library path)."""
    ee = context.get("execution_evidence") or {}
    if isinstance(ee.get("pipeline_run"), dict):
        return ee["pipeline_run"], "execution_evidence.pipeline_run"
    if any(k in ee for k in ("logs", "steps")):
        return ee, "execution_evidence"
    return None, ""


def evidence_catalog(context: dict[str, Any]) -> list[dict[str, str]]:
    """Stable IDs the LLM must cite, each pointing at a location in the evidence package."""
    cat = []
    ee = context.get("execution_evidence") or {}
    if "execution_summary" in ee:
        cat.append({"id": "pipeline.execution_summary", "location": "execution_evidence.execution_summary"})
    run, loc = _run_record(context)
    if run is not None:
        cat.append({"id": "pipeline.run_log", "location": loc})
    if "validation_summary" in context:
        cat.append({"id": "validation.summary", "location": "validation_summary"})
    for i, v in enumerate(context.get("validation_results", [])):
        cat.append({"id": f"validation.{_slug(v.get('name') or v.get('check') or f'check_{i}')}",
                    "location": f"validation_results[{i}]"})
    for side in ("source", "target"):
        if side in context:
            cat.append({"id": f"dataset.{side}", "location": side})
    # Upload runs (src/runs/service.py): each evidence line's own ID, the target schema and the upload profile.
    for i, v in enumerate(context.get("validation_results", [])):
        for j, line in enumerate(v.get("evidence") or []):
            m = re.match(r"\[(validation\.[A-Za-z0-9_]+\.\d+)\]", str(line))
            if m:
                cat.append({"id": m.group(1), "location": f"validation_results[{i}].evidence[{j}]"})
    if "target_table" in context:
        cat.append({"id": "dataset.target_table", "location": "target_table"})
    if "upload" in context:
        cat.append({"id": "dataset.upload", "location": "upload"})
    for key, eid in (("column_profiles", "dataset.column_profiles"), ("failing_rows", "dataset.failing_rows"),
                     ("target_data", "dataset.target_data"), ("run_history", "pipeline.run_history")):
        if key in context:
            cat.append({"id": eid, "location": key})
    return cat


def build_user_prompt(context: dict[str, Any]) -> str:
    return (
        "Investigate this pipeline using ONLY the evidence package below; cite IDs from available_evidence.\n\n"
        + json.dumps(context, indent=2, default=str)
    )


def parse_llm_json(text: str) -> dict[str, Any]:
    """Extract the JSON object from an LLM response (tolerates code fences / surrounding prose)."""
    if not text or not text.strip():
        raise InvestigationParseError("LLM returned an empty response")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise InvestigationParseError(f"No JSON object in LLM response: {text[:200]!r}")
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as e:
            raise InvestigationParseError(f"Invalid JSON in LLM response: {e}") from e


# --- post-checks on the LLM output ------------------------------------------------------------

def evidence_warnings(result: InvestigationResult, known_ids: set[str]) -> list[str]:
    """Flag citations that don't match supplied evidence IDs, and inconsistent conclusions.

    Warnings are reported to the caller; the LLM output itself is never rewritten.
    """
    warnings = []
    groups = [("observed_facts", result.observed_facts), ("root_cause_evidence", result.root_cause_evidence)]
    groups += [(f"hypotheses[{i}].evidence", h.evidence) for i, h in enumerate(result.hypotheses)]
    groups += [(f"cause_groups[{i}].evidence", g.evidence) for i, g in enumerate(result.cause_groups)]
    groups += [(f"row_fixes[{i}].evidence", [f.evidence]) for i, f in enumerate(result.row_fixes) if f.evidence]
    for field_name, items in groups:
        for j, text in enumerate(items):
            refs = _EVIDENCE_REF.findall(text)
            if not refs:
                warnings.append(f"{field_name}[{j}] cites no evidence ID")
            unknown = sorted({r for r in refs if r not in known_ids})
            if unknown:
                warnings.append(f"{field_name}[{j}] cites unknown evidence ID(s): {', '.join(unknown)}")
    if not 2 <= len(result.hypotheses) <= 3:
        warnings.append(f"expected 2-3 hypotheses, got {len(result.hypotheses)}")
    if result.root_cause_status == "IDENTIFIED":
        if not result.root_cause_evidence:
            warnings.append("root cause marked IDENTIFIED but root_cause_evidence is empty")
        if not any(h.status == "SUPPORTED" for h in result.hypotheses):
            warnings.append("root cause marked IDENTIFIED but no hypothesis is SUPPORTED")
    return warnings


def _data_note(context: dict[str, Any]) -> str:
    rows = context.get("failing_rows")
    if rows is None:
        return "Datasets sent as summaries (row counts, columns, null counts), not raw rows."
    return (f"The uploaded file was sent as column profiles; only the {rows['rows_sent']} row(s) named by failed "
            f"checks were sent in full (of {rows['rows_in_file']} rows).")


def build_trace(context: dict[str, Any], result: InvestigationResult, provider: LLMProvider,
                attempts: int, rejected: list[str]) -> list[TraceStep]:
    """The real stages this service executed. Stages 3-7 happen inside ONE LLM call."""
    ids = [e["id"] for e in context["available_evidence"]]
    vs = context["validation_summary"]
    run, _ = _run_record(context)
    model = getattr(provider, "model", None)
    llm = type(provider).__name__ + (f" ({model})" if model else "")
    counts = {s: sum(h.status == s for h in result.hypotheses) for s in HYPOTHESIS_STATUSES}
    n_cited = len(result.observed_facts) + len(result.root_cause_evidence) + sum(len(h.evidence) for h in result.hypotheses)

    validation = f"{vs['failed_checks']} of {vs['total_checks']} deterministic validation checks FAILED"
    if vs["failed_check_names"]:
        validation += f" ({', '.join(vs['failed_check_names'])})"
    if run is not None and run.get("status"):
        validation += f"; pipeline execution record reports status={run['status']}"
    generation = f"{llm} returned {len(result.hypotheses)} hypotheses in a single structured call"
    if attempts > 1:
        generation += f" on attempt {attempts} (earlier output rejected: {rejected[0]})"

    return [
        TraceStep("evidence_collection",
                  f"Assembled {len(ids)} evidence items: {', '.join(ids)}. " + _data_note(context)),
        TraceStep("validation_analysis", validation + "."),
        TraceStep("hypothesis_generation", generation + "."),
        TraceStep("evidence_correlation",
                  f"Hypotheses evaluated against cited evidence: "
                  + ", ".join(f"{n} {s}" for s, n in counts.items())
                  + f". Citation check: {n_cited} evidence entries checked, "
                    f"{len(result.evidence_warnings)} warning(s)."),
        TraceStep("root_cause_analysis",
                  f"Root cause {result.root_cause_status} with {len(result.root_cause_evidence)} cited evidence entries."),
        TraceStep("remediation_generation", "Recommended fix generated by the LLM. It has not been applied."),
        TraceStep("regression_test_generation",
                  f"Regression test '{result.regression_test.name}' generated by the LLM. It has not been executed."),
    ]


# --- entry points -----------------------------------------------------------------------------

def investigate(
    pipeline_description: str,
    source: pd.DataFrame,
    target: pd.DataFrame,
    execution_evidence: dict[str, Any],
    validation_results: list[ValidationResult] | None = None,
    provider: LLMProvider | None = None,
) -> InvestigationResult:
    """Run validations (if not supplied), send all evidence to the LLM, return a structured result."""
    if validation_results is None:
        validation_results = run_all_validations(source, target)
    context = build_context(pipeline_description, source, target, validation_results, execution_evidence)
    return _ask_llm(context, provider)


def investigate_pipeline(
    pipeline_name: str,
    pipeline_description: str,
    execution_summary: dict[str, Any],
    validation_results: list[dict[str, Any]],
    use_demo_data: bool = False,
    provider: LLMProvider | None = None,
) -> InvestigationResult:
    """Investigate from caller-supplied evidence (JSON-friendly; used by the API).

    If use_demo_data is True, the bundled scenario data is summarised, its pipeline run log is
    added as execution evidence, and run_demo_validation_suite() (the same suite behind
    GET /api/demo/scenario) supplies the validation results. Suite results are authoritative:
    caller-supplied results with the same check name are replaced, not duplicated.
    """
    context: dict[str, Any] = {
        "pipeline_name": pipeline_name,
        "pipeline_description": pipeline_description,
        "execution_evidence": {"execution_summary": execution_summary},
        "validation_results": list(validation_results),
    }
    if use_demo_data:
        source, target, run = load_scenario()
        context["source"] = _profile(source)
        context["target"] = _profile(target)
        context["execution_evidence"]["pipeline_run"] = run
        suite_results = run_demo_validation_suite()["results"]
        suite_names = {r["name"] for r in suite_results}
        context["validation_results"] = [
            v for v in context["validation_results"] if v.get("name") not in suite_names
        ] + suite_results
    return _ask_llm(context, provider)


def investigate_evidence(context: dict[str, Any], provider: LLMProvider | None = None,
                         system_prompt: str = SYSTEM_PROMPT,
                         required: tuple[str, ...] = REQUIRED_KEYS) -> InvestigationResult:
    """Investigate a ready-made evidence package (upload runs, see src/runs/service.py)."""
    return _ask_llm(context, provider, system_prompt, required)


def _ask_llm(context: dict[str, Any], provider: LLMProvider | None, system_prompt: str = SYSTEM_PROMPT,
             required: tuple[str, ...] = REQUIRED_KEYS) -> InvestigationResult:
    provider = provider or get_provider()
    context = {**context, "validation_summary": summarize_validations(context.get("validation_results", []))}
    context["available_evidence"] = evidence_catalog(context)
    user_prompt = build_user_prompt(context)

    system, rejected = system_prompt, []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = provider.complete(system, user_prompt)
        try:
            result = InvestigationResult.from_dict(parse_llm_json(raw), raw_response=raw, required=required)
            break
        except InvestigationParseError as e:
            rejected.append(str(e))
            if attempt == MAX_ATTEMPTS:
                raise InvestigationParseError(f"{e} (after {attempt} attempts)") from e
            system = system_prompt + RETRY_NOTE.format(error=e)

    result.evidence_warnings = evidence_warnings(result, {e["id"] for e in context["available_evidence"]})
    result.investigation_trace = build_trace(context, result, provider, attempt, rejected)
    result.model = str(getattr(provider, "model", "") or "")
    return result


def investigate_scenario(provider: LLMProvider | None = None) -> InvestigationResult:
    """Convenience entry point for the bundled demo scenario (same path as use_demo_data=true)."""
    source, target, _ = load_scenario()
    return investigate_pipeline(
        PIPELINE_NAME, PIPELINE_DESCRIPTION,
        execution_summary={"source_records": len(source), "target_records": len(target)},
        validation_results=[], use_demo_data=True, provider=provider,
    )
