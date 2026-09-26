"""FastAPI app.  Run:  uvicorn src.api.main:app --reload --env-file .env"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from typing import Callable

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.ai.provider import LLMError, LLMProvider, LLMTimeoutError, get_provider
from src.api.schemas import (
    DemoRunResponse, DemoScenarioResponse, HealthResponse, InvestigateRequest, InvestigateResponse,
    RunSummary, TargetListResponse, TargetSchemaResponse,
)
from src.config import cors_origins, target_db_path
from src.investigation.models import InvestigationParseError
from src.investigation.service import investigate_pipeline
from src.runs.ingest import UploadError, check_file_type, parse_csv, read_limited
from src.runs.service import validate_run
from src.runs.store import RunRecord, RunStore, new_run_id, store
from src.target.database import initialize_database
from src.target.discovery import discover_schema
from src.target.registry import TARGETS, get_target
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


# --- targets ---------------------------------------------------------------------------------
# New (non-demo) endpoints report errors as detail = {"code", "message", "field"}.

def get_target_db() -> str:
    """FastAPI dependency: path of the SQLite target database, created and seeded if missing."""
    return str(initialize_database(target_db_path()))


def api_error(status_code: int, code: str, message: str, field: str | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "field": field})


@app.get("/api/targets", response_model=TargetListResponse)
def list_targets() -> dict:
    """The target tables a file can be loaded into (identification only, no schema)."""
    return {"targets": [t.to_dict() for t in TARGETS.values()]}


@app.get("/api/targets/{target_id}", response_model=TargetSchemaResponse, response_model_exclude_none=True)
def target_schema(target_id: str, db: str = Depends(get_target_db)) -> dict:
    """The target's columns and constraints, discovered from the SQLite database."""
    target = get_target(target_id)
    if target is None:
        raise api_error(404, "target_not_found", f"Target '{target_id}' was not found.", "target_id")
    with closing(sqlite3.connect(db)) as conn:
        schema = discover_schema(conn, target.table_name)
    return {"target_id": target.target_id, "table_name": target.table_name,
            "database_type": target.database_type, **schema}


# --- runs ------------------------------------------------------------------------------------

def get_run_store() -> RunStore:
    """FastAPI dependency: the in-memory run store. Tests override it."""
    return store


@app.post("/api/runs", response_model=RunSummary, status_code=201)
def create_run(
    target_id: str = Form(...),
    file: UploadFile = File(...),
    runs: RunStore = Depends(get_run_store),
    db: str = Depends(get_target_db),
) -> dict:
    """Upload one CSV for a target, create a run and validate it against the target's discovered schema.

    A file that can't be read creates no run. The target table is only read, never written."""
    target = get_target(target_id)
    if target is None:
        raise api_error(404, "target_not_found", f"Target '{target_id}' was not found.", "target_id")
    try:
        check_file_type(file.filename)
        upload = parse_csv(read_limited(file.file))
    except UploadError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail()) from e
    record = RunRecord(run_id=new_run_id(), target_id=target.target_id, target_table=target.table_name,
                       file_name=file.filename, upload=upload)
    runs.add(record)
    with closing(sqlite3.connect(db)) as conn:
        schema = discover_schema(conn, target.table_name)
    validate_run(record, schema)
    return record.to_summary()


@app.get("/api/runs/{run_id}", response_model=RunSummary)
def get_run(run_id: str, runs: RunStore = Depends(get_run_store)) -> dict:
    record = runs.get(run_id)
    if record is None:
        raise api_error(404, "run_not_found", f"Run '{run_id}' was not found.", "run_id")
    return record.to_summary()
