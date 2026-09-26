"""Pydantic request/response models: the HTTP contract shared with the React frontend."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.investigation.models import InvestigationResult

HypothesisStatus = Literal["supported", "rejected", "inconclusive"]
_STATUS_MAP = {"confirmed": "supported", "supported": "supported", "rejected": "rejected"}


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(extra="allow")  # any extra run metrics / logs are passed through

    source_records: int | None = Field(default=None, ge=0)
    target_records: int | None = Field(default=None, ge=0)


class ValidationResultIn(BaseModel):
    name: str = Field(min_length=1)
    status: str = Field(min_length=1, description="e.g. PASSED, FAILED, WARNING")
    details: str = ""


class InvestigateRequest(BaseModel):
    pipeline_name: str = Field(min_length=1)
    pipeline_description: str = Field(min_length=1)
    execution_summary: ExecutionSummary = Field(default_factory=ExecutionSummary)
    validation_results: list[ValidationResultIn] = Field(default_factory=list)
    use_demo_data: bool = Field(
        default=False,
        description="Also run the deterministic validation tools on the bundled demo pipeline data.",
    )

    @model_validator(mode="after")
    def _needs_evidence(self) -> "InvestigateRequest":
        if not self.validation_results and not self.use_demo_data:
            raise ValueError("Provide at least one validation result, or set use_demo_data=true.")
        return self


class HypothesisOut(BaseModel):
    hypothesis: str
    evidence: list[str]
    status: HypothesisStatus


class InvestigateResponse(BaseModel):
    summary: str
    hypotheses: list[HypothesisOut]
    root_cause: str
    evidence: list[str]
    recommended_fix: str
    regression_test: str

    @classmethod
    def from_result(cls, r: InvestigationResult) -> "InvestigateResponse":
        test = r.regression_test
        header = f"# {test.name}: {test.description}\n" if test.description else ""
        return cls(
            summary=r.summary,
            hypotheses=[
                HypothesisOut(
                    hypothesis=h.statement,
                    evidence=h.supporting_evidence + [f"Contradicts: {e}" for e in h.contradicting_evidence],
                    status=_STATUS_MAP.get(h.status, "inconclusive"),
                )
                for h in r.hypotheses
            ],
            root_cause=r.root_cause,
            evidence=[f"{e.source}: {e.observation}" for e in r.evidence],
            recommended_fix=r.recommended_fix,
            regression_test=header + test.code,
        )


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    llm_configured: bool
    details: dict[str, Any] = Field(default_factory=dict)
