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


# --- upload runs: single file -> existing SQLite target table ---------------------------------

RunStatus = Literal["SUCCESS", "FAILED"]


class ApiErrorDetail(BaseModel):
    """`detail` of every error from the /api/targets and /api/runs endpoints."""

    code: str
    message: str
    field: str | None = None


class TargetColumn(BaseModel):
    name: str
    type: str
    affinity: Literal["INTEGER", "TEXT", "BLOB", "REAL", "NUMERIC"]
    not_null: bool
    default: str | None
    primary_key: bool
    unique: bool


class CheckConstraintOut(BaseModel):
    name: str
    expression: str


class TargetSummary(BaseModel):
    name: str
    row_count: int
    column_count: int


class TargetDetail(BaseModel):
    name: str
    ddl: str
    row_count: int
    columns: list[TargetColumn]
    primary_key: list[str]
    unique_keys: list[list[str]]
    check_constraints: list[CheckConstraintOut]
    sample_rows: list[dict[str, Any]]


class RowIssue(BaseModel):
    line: int | None = Field(description="Line in the uploaded file (the header is line 1); null for file-level issues.")
    column: str | None
    value: Any = None
    check: str
    message: str


class RetryComparison(BaseModel):
    previous_run_id: str
    previous_status: RunStatus
    resolved_checks: list[str]
    still_failing_checks: list[str]
    new_failing_checks: list[str]


class RunDetail(BaseModel):
    run_id: str
    created_at: str
    status: RunStatus
    failed_stage: Literal["schema_check", "validate", "load"] | None
    target_table: str
    file_name: str
    retry_of: str | None
    row_count: int
    columns: list[str]
    rows_loaded: int
    target_rows_before: int
    target_rows_after: int
    load_error: str | None
    validation_summary: ValidationSummary
    validation_results: list[CheckResultOut]
    row_issues: list[RowIssue]
    row_issues_truncated: bool
    retry_comparison: RetryComparison | None
    preview: list[dict[str, Any]]
    pipeline_run: dict[str, Any]
    investigation: InvestigateResponse | None


class RunListItem(BaseModel):
    run_id: str
    created_at: str
    status: RunStatus
    failed_stage: str | None
    target_table: str
    file_name: str
    retry_of: str | None
    row_count: int
    rows_loaded: int
    investigated: bool
