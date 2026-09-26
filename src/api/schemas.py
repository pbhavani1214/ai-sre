"""Pydantic request/response models: the HTTP contract shared with the React frontend."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.investigation.models import InvestigationResult

HypothesisStatus = Literal["SUPPORTED", "REJECTED", "INCONCLUSIVE"]


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(extra="allow")  # any extra run metrics / logs are passed through

    source_records: int | None = Field(default=None, ge=0)
    target_records: int | None = Field(default=None, ge=0)


class ValidationResultIn(BaseModel):
    """Accepts the simple {name, status, details} form, or a full CheckResult from /api/demo/scenario."""

    name: str = Field(min_length=1)
    status: str = Field(min_length=1, description="e.g. PASSED, FAILED, WARNING")
    details: str = Field(default="", max_length=2000)
    severity: str | None = None
    summary: str | None = Field(default=None, max_length=1000)
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list, max_length=20)


class InvestigateRequest(BaseModel):
    pipeline_name: str = Field(min_length=1)
    pipeline_description: str = Field(min_length=1)
    execution_summary: ExecutionSummary = Field(default_factory=ExecutionSummary)
    validation_results: list[ValidationResultIn] = Field(default_factory=list, max_length=50)
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
    status: HypothesisStatus
    evidence: list[str]
    reasoning: str


class TraceStepOut(BaseModel):
    stage: str
    description: str


class InvestigateResponse(BaseModel):
    summary: str
    observed_facts: list[str]
    hypotheses: list[HypothesisOut]
    root_cause_status: Literal["IDENTIFIED", "INCONCLUSIVE"]
    root_cause: str
    root_cause_evidence: list[str]
    root_cause_reasoning: str
    evidence: list[str] = Field(description="Backward-compatible alias of observed_facts.")
    recommended_fix: str
    regression_test: str
    investigation_trace: list[TraceStepOut]
    evidence_warnings: list[str] = Field(
        description="Citations that don't match supplied evidence IDs, or inconsistent conclusions.")

    @classmethod
    def from_result(cls, r: InvestigationResult) -> "InvestigateResponse":
        test = r.regression_test
        header = f"# {test.name}: {test.description}\n" if test.description else ""
        return cls(
            summary=r.summary,
            observed_facts=r.observed_facts,
            hypotheses=[
                HypothesisOut(hypothesis=h.statement, status=h.status, evidence=h.evidence, reasoning=h.reasoning)
                for h in r.hypotheses
            ],
            root_cause_status=r.root_cause_status,
            root_cause=r.root_cause,
            root_cause_evidence=r.root_cause_evidence,
            root_cause_reasoning=r.root_cause_reasoning,
            evidence=r.observed_facts,
            recommended_fix=r.recommended_fix,
            regression_test=header + test.code,
            investigation_trace=[TraceStepOut(stage=t.stage, description=t.description) for t in r.investigation_trace],
            evidence_warnings=r.evidence_warnings,
        )


class CheckResultOut(BaseModel):
    name: str
    status: Literal["PASSED", "FAILED"]
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    summary: str
    metrics: dict[str, Any]
    evidence: list[str]


class ValidationSummary(BaseModel):
    total_checks: int
    passed_checks: int
    failed_checks: int


class DemoScenarioResponse(BaseModel):
    pipeline_name: str
    pipeline_description: str
    status: Literal["PASSED", "FAILED"]
    execution_summary: ExecutionSummary
    validation_summary: ValidationSummary
    validation_results: list[CheckResultOut]


class DemoRunResponse(BaseModel):
    pipeline_run: dict[str, Any]
    source: list[dict[str, Any]]
    target: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    llm_configured: bool
    details: dict[str, Any] = Field(default_factory=dict)


# --- targets (CONTRACT.md: Target Selection API, Target Schema API) --------------------------

class ApiErrorDetail(BaseModel):
    """`detail` of every error from the live (non-demo) endpoints."""

    code: str
    message: str
    field: str | None = None


class TargetOut(BaseModel):
    target_id: str
    table_name: str
    display_name: str
    description: str | None = None
    database_type: Literal["sqlite"]


class TargetListResponse(BaseModel):
    targets: list[TargetOut]


class TargetColumnOut(BaseModel):
    name: str
    data_type: str
    nullable: bool
    primary_key: bool
    unique: bool


class TargetConstraintOut(BaseModel):
    type: Literal["PRIMARY_KEY", "UNIQUE", "NOT_NULL", "CHECK"]
    columns: list[str]
    allowed_values: list[str] | None = None  # CHECK constraints of the form `column IN (...)` only
    description: str


class TargetSchemaResponse(BaseModel):
    target_id: str
    table_name: str
    database_type: Literal["sqlite"]
    columns: list[TargetColumnOut]
    constraints: list[TargetConstraintOut]
