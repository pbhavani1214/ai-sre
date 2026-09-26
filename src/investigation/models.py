"""Structured investigation result model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

REQUIRED_KEYS = ("summary", "hypotheses", "evidence", "root_cause", "recommended_fix", "regression_test")


class InvestigationParseError(ValueError):
    pass


@dataclass
class Hypothesis:
    statement: str
    status: str  # "confirmed" | "rejected" | "inconclusive"
    confidence: float  # 0.0 - 1.0
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Hypothesis":
        try:
            confidence = max(0.0, min(1.0, float(d.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        return cls(
            statement=str(d.get("statement", "")),
            status=str(d.get("status", "inconclusive")).lower(),
            confidence=confidence,
            supporting_evidence=[str(x) for x in d.get("supporting_evidence", []) or []],
            contradicting_evidence=[str(x) for x in d.get("contradicting_evidence", []) or []],
        )


@dataclass
class Evidence:
    source: str  # e.g. a validation check name, "pipeline_run.logs", "pipeline_run.config"
    observation: str

    @classmethod
    def from_dict(cls, d: dict[str, Any] | str) -> "Evidence":
        if isinstance(d, str):
            return cls(source="unspecified", observation=d)
        return cls(source=str(d.get("source", "unspecified")), observation=str(d.get("observation", "")))


@dataclass
class RegressionTest:
    name: str
    description: str
    code: str  # python test source, NOT executed by this system

    @classmethod
    def from_dict(cls, d: dict[str, Any] | str) -> "RegressionTest":
        if isinstance(d, str):
            return cls(name="regression_test", description="", code=d)
        return cls(name=str(d.get("name", "regression_test")), description=str(d.get("description", "")),
                   code=str(d.get("code", "")))


@dataclass
class InvestigationResult:
    summary: str
    hypotheses: list[Hypothesis]
    evidence: list[Evidence]
    root_cause: str
    recommended_fix: str
    regression_test: RegressionTest
    raw_response: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any], raw_response: str = "") -> "InvestigationResult":
        missing = [k for k in REQUIRED_KEYS if k not in d]
        if missing:
            raise InvestigationParseError(f"LLM output missing required keys: {missing}")
        return cls(
            summary=str(d["summary"]),
            hypotheses=[Hypothesis.from_dict(h) for h in d["hypotheses"] or []],
            evidence=[Evidence.from_dict(e) for e in d["evidence"] or []],
            root_cause=str(d["root_cause"]),
            recommended_fix=str(d["recommended_fix"]),
            regression_test=RegressionTest.from_dict(d["regression_test"]),
            raw_response=raw_response,
        )

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("raw_response")
        return out
