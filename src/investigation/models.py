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
# Upload runs: the regression test is generated from the target schema instead. The AI's cause_groups, row_fixes and
# prevention are requested but optional, so a model that omits them still gives a usable investigation.
RUN_REQUIRED_KEYS = tuple(k for k in REQUIRED_KEYS if k != "regression_test")


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


FIX_ACTIONS = ("REPLACE", "DELETE_ROW", "NEEDS_DECISION")
CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")


def _optional_list(d: dict[str, Any], key: str) -> list[Any]:
    v = d.get(key, [])
    if v is None:
        return []
    if not isinstance(v, list):
        raise InvestigationParseError(f"'{key}' must be a list")
    return v


@dataclass
class CauseGroup:
    """Failures grouped by their likely origin (upload runs only)."""
    title: str
    category: str
    explanation: str
    checks: list[str] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Any, i: int = 0) -> "CauseGroup":
        where = f"cause_groups[{i}]."
        if not isinstance(d, dict):
            raise InvestigationParseError(f"'cause_groups[{i}]' must be an object")
        rows = d.get("rows") or []
        if not isinstance(rows, list):
            raise InvestigationParseError(f"'{where}rows' must be a list of row numbers")
        return cls(
            title=_text(d, "title", where),
            category=str(d.get("category") or "OTHER").strip().upper(),
            explanation=_text(d, "explanation", where),
            checks=_text_list(d, "checks", where) if d.get("checks") is not None else [],
            rows=[int(r) for r in rows if str(r).strip().lstrip("+-").isdigit()],
            evidence=_text_list(d, "evidence", where) if d.get("evidence") is not None else [],
        )


@dataclass
class RowFix:
    """One suggested correction to the uploaded file (upload runs only). Never applied automatically."""
    row: int
    column: str | None
    action: str  # one of FIX_ACTIONS
    current_value: str | None
    suggested_value: str | None
    reason: str
    confidence: str  # one of CONFIDENCE_LEVELS
    evidence: str = ""
    satisfies_constraints: bool = False  # set by the backend after checking the suggestion

    @classmethod
    def from_dict(cls, d: Any, i: int = 0) -> "RowFix":
        where = f"row_fixes[{i}]."
        if not isinstance(d, dict):
            raise InvestigationParseError(f"'row_fixes[{i}]' must be an object")
        try:
            row = int(d.get("row"))
        except (TypeError, ValueError):
            raise InvestigationParseError(f"'{where}row' must be a row number") from None
        action = str(d.get("action") or "").strip().upper()
        if action not in FIX_ACTIONS:
            raise InvestigationParseError(f"'{where}action' is {d.get('action')!r}; expected one of {', '.join(FIX_ACTIONS)}")
        confidence = str(d.get("confidence") or "LOW").strip().upper()
        if confidence not in CONFIDENCE_LEVELS:
            confidence = "LOW"
        suggested = d.get("suggested_value")
        if action == "REPLACE" and suggested is None:
            raise InvestigationParseError(f"'{where}suggested_value' is required for REPLACE")
        column = d.get("column")
        return cls(
            row=row,
            column=str(column) if column not in (None, "") else None,
            action=action,
            current_value=None if d.get("current_value") is None else str(d["current_value"]),
            suggested_value=None if suggested is None or action != "REPLACE" else str(suggested),
            reason=_text(d, "reason", where),
            confidence=confidence,
            evidence=str(d.get("evidence") or "").strip(),
        )


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
    # Upload runs only (src/runs/service.py); empty for the pipeline investigation:
    cause_groups: list[CauseGroup] = field(default_factory=list)
    row_fixes: list[RowFix] = field(default_factory=list)
    prevention: list[str] = field(default_factory=list)
    model: str = ""  # the model that produced the result

    @classmethod
    def from_dict(cls, d: Any, raw_response: str = "",
                  required: tuple[str, ...] = REQUIRED_KEYS) -> "InvestigationResult":
        if not isinstance(d, dict):
            raise InvestigationParseError("LLM output must be a JSON object")
        missing = [k for k in required if k not in d]
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
            regression_test=(RegressionTest.from_dict(d["regression_test"]) if "regression_test" in d
                             else RegressionTest(name="regression_test", description="", code="")),
            raw_response=raw_response,
            cause_groups=[CauseGroup.from_dict(g, i) for i, g in enumerate(_optional_list(d, "cause_groups"))],
            row_fixes=[RowFix.from_dict(f, i) for i, f in enumerate(_optional_list(d, "row_fixes"))],
            prevention=[str(p).strip() for p in _optional_list(d, "prevention") if str(p).strip()],
        )

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("raw_response")
        return out
