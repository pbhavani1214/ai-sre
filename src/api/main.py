"""FastAPI app.  Run:  uvicorn src.api.main:app --reload --env-file .env"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.ai.provider import LLMError, LLMProvider, LLMTimeoutError, get_provider
from src.api.schemas import (
    DemoRunResponse, DemoScenarioResponse, HealthResponse, InvestigateRequest, InvestigateResponse,
    RunSummary, UploadErrorResponse,
)
from src.config import cors_origins
from src.investigation.models import InvestigationParseError
from src.investigation.service import investigate_pipeline
from src.runs import ingest  # limits read via the module so tests can monkeypatch them
from src.runs.ingest import UploadError, parse_csv, parse_pipeline_run, read_limited
from src.runs.store import RunRecord, RunStore, get_run_store, new_run_id
from src.runs.summary import summarize
from src.validation.suite import get_demo_run, get_demo_scenario

log = logging.getLogger(__name__)

app = FastAPI(title="AI Software Reliability Engineer", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def get_llm_provider() -> Callable[[], LLMProvider]:
    """FastAPI dependency returning a provider factory (env config). Tests override this at the boundary.

    A factory rather than a provider, so a missing key surfaces only after the request body
    has been validated (invalid requests get 422, not 503).
    """
    return get_provider


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        provider = get_provider()
        return HealthResponse(llm_configured=True, details={"provider": type(provider).__name__,
                                                            "model": getattr(provider, "model", None)})
    except LLMError as e:
        return HealthResponse(llm_configured=False, details={"error": str(e)})


@app.get("/api/demo/scenario", response_model=DemoScenarioResponse)
def demo_scenario() -> dict:
    """Deterministic demo state (real validation suite on bundled data). Never calls the LLM."""
    return get_demo_scenario()


@app.get("/api/demo/run", response_model=DemoRunResponse)
def demo_run() -> dict:
    """Raw demo inputs (pipeline run record, source and target rows) for the UI. Never calls the LLM."""
    return get_demo_run()


@app.post("/api/investigate", response_model=InvestigateResponse)
def investigate(
    req: InvestigateRequest, make_provider: Callable[[], LLMProvider] = Depends(get_llm_provider)
) -> InvestigateResponse:
    try:
        provider = make_provider()
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"LLM not configured: {e}") from e
    try:
        result = investigate_pipeline(
            pipeline_name=req.pipeline_name,
            pipeline_description=req.pipeline_description,
            execution_summary=req.execution_summary.model_dump(exclude_none=True),
            validation_results=[v.model_dump() for v in req.validation_results],
            use_demo_data=req.use_demo_data,
            provider=provider,
        )
    except InvestigationParseError as e:
        log.warning("Unparseable LLM output: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM returned an invalid investigation: {e}") from e
    except LLMTimeoutError as e:
        log.warning("LLM timed out: %s", e)
        raise HTTPException(status_code=504, detail=f"LLM provider timed out: {e}") from e
    except LLMError as e:
        log.warning("LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM provider unavailable: {e}") from e
    except Exception as e:  # never leak a stack trace to the frontend
        log.exception("Investigation failed unexpectedly")
        raise HTTPException(status_code=500, detail="Investigation failed due to an internal error.") from e
    return InvestigateResponse.from_result(result)


# --- Phase 1: uploaded runs -------------------------------------------------------------------

_UPLOAD_ERRORS = {413: {"model": UploadErrorResponse}, 422: {"model": UploadErrorResponse}}


def _file_name(upload: UploadFile, default: str) -> str:
    return (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1] or default


@app.post("/api/runs", response_model=RunSummary, status_code=201, responses=_UPLOAD_ERRORS)
def create_run(
    source_file: UploadFile = File(...),
    target_file: UploadFile = File(...),
    pipeline_run_file: UploadFile | None = File(None),
    runs: RunStore = Depends(get_run_store),
) -> dict:
    """Upload source + target CSVs and an optional run log. Validated in contract order."""
    try:
        source = parse_csv(read_limited(source_file, ingest.MAX_CSV_BYTES, "source_file"), "source_file")
        target = parse_csv(read_limited(target_file, ingest.MAX_CSV_BYTES, "target_file"), "target_file")
        pipeline_run = None
        # A browser sends an empty part (no filename, no bytes) when no file was chosen.
        if pipeline_run_file is not None and pipeline_run_file.filename:
            pipeline_run = parse_pipeline_run(
                read_limited(pipeline_run_file, ingest.MAX_RUN_LOG_BYTES, "pipeline_run_file"))
    except UploadError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail()) from e

    record = RunRecord(
        run_id=new_run_id(),
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
        source_name=_file_name(source_file, "source.csv"),
        target_name=_file_name(target_file, "target.csv"),
        source=source,
        target=target,
        pipeline_run=pipeline_run,
    )
    runs.add(record)
    return summarize(record)


@app.get("/api/runs/{run_id}", response_model=RunSummary, responses={404: {"model": UploadErrorResponse}})
def get_run(run_id: str, runs: RunStore = Depends(get_run_store)) -> dict:
    record = runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail={
            "code": "run_not_found",
            "message": f"Run {run_id} was not found. It may have expired; upload the files again.",
            "field": None,
        })
    return summarize(record)
