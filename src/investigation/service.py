"""Investigation service: gathers deterministic evidence and asks the LLM to reason over it."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.ai.provider import LLMProvider, get_provider
from src.data.scenario import DATA_DIR, PIPELINE_DESCRIPTION, load_scenario
from src.investigation.models import InvestigationParseError, InvestigationResult
from src.validation.tools import ValidationResult, run_all_validations

SYSTEM_PROMPT = """You are an AI Software Reliability Engineer investigating a failed data pipeline.
Reason ONLY from the evidence provided (validation results, data profiles, pipeline run config/steps/logs).
Do not invent facts. Cite the specific evidence source for every claim.

Method:
1. Summarise what is wrong versus the pipeline's expected contract.
2. Form multiple competing hypotheses (there may be more than one defect).
3. For each hypothesis, state which evidence supports or contradicts it and mark it
   "confirmed", "rejected" or "inconclusive" with a confidence between 0 and 1.
4. Identify the most likely root cause(s), recommend a concrete fix, and write a pytest
   regression test (pandas) that would fail on the current behaviour and pass after the fix.

Respond with a single JSON object and nothing else, using exactly this schema:
{
  "summary": "string",
  "hypotheses": [{"statement": "string", "status": "confirmed|rejected|inconclusive",
                  "confidence": 0.0, "supporting_evidence": ["string"], "contradicting_evidence": ["string"]}],
  "evidence": [{"source": "string", "observation": "string"}],
  "root_cause": "string",
  "recommended_fix": "string",
  "regression_test": {"name": "string", "description": "string", "code": "string"}
}"""


def _profile(df: pd.DataFrame, max_rows: int = 30) -> dict[str, Any]:
    return {
        "row_count": len(df),
        "columns": list(df.columns),
        "null_counts": {c: int(n) for c, n in df.isna().sum().items()},
        "rows": df.head(max_rows).astype(object).where(df.head(max_rows).notna(), None).to_dict("records"),
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


def build_user_prompt(context: dict[str, Any]) -> str:
    return (
        "Investigate this pipeline failure. Evidence follows as JSON.\n\n"
        + json.dumps(context, indent=2, default=str)
    )


def parse_llm_json(text: str) -> dict[str, Any]:
    """Extract the JSON object from an LLM response (tolerates code fences / surrounding prose)."""
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

    If use_demo_data is True, the bundled scenario data is also profiled, the deterministic
    validation tools are run on it, and its pipeline run log is added as execution evidence.
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
        context["validation_results"] += [v.to_dict() for v in run_all_validations(source, target)]
    return _ask_llm(context, provider)


def _ask_llm(context: dict[str, Any], provider: LLMProvider | None) -> InvestigationResult:
    provider = provider or get_provider()
    raw = provider.complete(SYSTEM_PROMPT, build_user_prompt(context))
    return InvestigationResult.from_dict(parse_llm_json(raw), raw_response=raw)


def investigate_scenario(data_dir: Path = DATA_DIR, provider: LLMProvider | None = None) -> InvestigationResult:
    """Convenience entry point for the bundled demo scenario."""
    source, target, run = load_scenario(data_dir)
    return investigate(PIPELINE_DESCRIPTION, source, target, execution_evidence=run, provider=provider)
