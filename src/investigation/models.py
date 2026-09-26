"""Structured investigation result model, parsed strictly from the LLM's JSON output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

HYPOTHESIS_STATUSES = ("SUPPORTED", "REJECTED", "INCONCLUSIVE")
ROOT_CAUSE_STATUSES = ("IDENTIFIED", "INCONCLUSIVE")
REQUIRED_KEYS = (
    "summary", "observed_facts", "hypotheses", "root_cause", "root_cause_evidence",
    "root_cause_reasoning", "recommended_fix", "regression_test",
)


class InvestigationParseError(ValueError):
    pass


def _text(d: dict[str, Any], key: str, where: str = "") -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise InvestigationParseError(f"'{where}{key}' must be a non-empty string")
    return v.strip()


def _text_list(d: dict[str, Any], key: str, where: str = "") -> list[str]:
    v = d.get(key)
    if not isinstance(v, list) or not all(isinstance(x, (str, int, float)) for x in v):
        raise InvestigationParseError(f"'{where}{key}' must be a list of strings")
    return [str(x).strip() for x in v if str(x).strip()]


@dataclass
class Hypothesis:
    statement: str
    status: str  # one of HYPOTHESIS_STATUSES
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""

    @classmethod
    def from_dict(cls, d: Any, i: int = 0) -> "Hypothesis":
        where = f"hypotheses[{i}]."
        if not isinstance(d, dict):
            raise InvestigationParseError(f"'hypotheses[{i}]' must be an object")
        status = str(d.get("status", "")).strip().upper()
        if status not in HYPOTHESIS_STATUSES:
            raise InvestigationParseError(
                f"'{where}status' is {d.get('status')!r}; expected one of {', '.join(HYPOTHESIS_STATUSES)}")
        return cls(
            statement=_text(d, "hypothesis", where),
            status=status,
            evidence=_text_list(d, "evidence", where),
            reasoning=_text(d, "reasoning", where),
        )


@dataclass
class RegressionTest:
    name: str
    description: str
    code: str  # python test source, NOT executed by this system

    @classmethod
    def from_dict(cls, d: dict[str, Any] | str) -> "RegressionTest":
        if isinstance(d, str) and d.strip():
            return cls(name="regression_test", description="", code=d)
        if isinstance(d, dict):
            return cls(name=str(d.get("name") or "regression_test"), description=str(d.get("description", "")),
                       code=_text(d, "code", "regression_test."))
        raise InvestigationParseError("'regression_test' must be a non-empty string or an object with 'code'")


@dataclass
class TraceStep:
    stage: str
    description: str


@dataclass
class InvestigationResult:
    summary: str
    observed_facts: list[str]
    hypotheses: list[Hypothesis]
    root_cause_status: str  # one of ROOT_CAUSE_STATUSES
    root_cause: str
    root_cause_evidence: list[str]
    root_cause_reasoning: str
    recommended_fix: str
    regression_test: RegressionTest
    # Filled in by the service (not by the LLM):
    investigation_trace: list[TraceStep] = field(default_factory=list)
    evidence_warnings: list[str] = field(default_factory=list)
    raw_response: str = ""

    @classmethod
    def from_dict(cls, d: Any, raw_response: str = "") -> "InvestigationResult":
        if not isinstance(d, dict):
            raise InvestigationParseError("LLM output must be a JSON object")
        missing = [k for k in REQUIRED_KEYS if k not in d]
        if missing:
            raise InvestigationParseError(f"LLM output missing required keys: {missing}")
        if not isinstance(d["hypotheses"], list) or not d["hypotheses"]:
            raise InvestigationParseError("'hypotheses' must be a non-empty list")

        root_cause = _text(d, "root_cause")
        rc_status = str(d.get("root_cause_status") or "IDENTIFIED").strip().upper()
        if rc_status not in ROOT_CAUSE_STATUSES:
            raise InvestigationParseError(
                f"'root_cause_status' is {d.get('root_cause_status')!r}; expected one of {', '.join(ROOT_CAUSE_STATUSES)}")
        return cls(
            summary=_text(d, "summary"),
            observed_facts=_text_list(d, "observed_facts"),
            hypotheses=[Hypothesis.from_dict(h, i) for i, h in enumerate(d["hypotheses"])],
            root_cause_status=rc_status,
            root_cause=root_cause,
            root_cause_evidence=_text_list(d, "root_cause_evidence"),
            root_cause_reasoning=_text(d, "root_cause_reasoning"),
            recommended_fix=_text(d, "recommended_fix"),
            regression_test=RegressionTest.from_dict(d["regression_test"]),
            raw_response=raw_response,
        )

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("raw_response")
        return out
