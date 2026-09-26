"""FastAPI app.  Run:  uvicorn src.api.main:app --reload --env-file .env"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from typing import Callable

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.ai.provider import LLMError, LLMProvider, LLMTimeoutError, get_provider
from src.api.schemas import (
    DemoRunResponse, DemoScenarioResponse, HealthResponse, InvestigateRequest, InvestigateResponse,
    RunDetail, RunListItem, TargetDetail, TargetSummary,
)
from src.config import cors_origins, target_db_path
from src.investigation.models import InvestigationParseError
from src.investigation.service import investigate_pipeline
from src.runs.ingest import UploadError, parse_csv, read_limited
from src.runs.investigate import investigate_run
from src.runs.pipeline import run_pipeline
from src.runs.store import RunRecord, RunStore, new_run_id, store
from src.target.demo import DEMO_UPLOAD_FILES, DEMO_UPLOADS_DIR, ensure_demo_database, reset_demo_database
from src.target.introspect import TargetNotFound, describe_table, list_tables, quote, row_count
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


# --- upload runs: single file -> existing SQLite target table ---------------------------------
# Errors from these endpoints use detail = {"code", "message", "field"} (ApiErrorDetail).

def get_target_db() -> str:
    """FastAPI dependency: path of the target database (created with demo data if missing)."""
    return str(ensure_demo_database(target_db_path()))


def get_run_store() -> RunStore:
    return store


def api_error(status_code: int, code: str, message: str, field: str | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "field": field})


def _target_not_found(table: str, field: str | None = None) -> HTTPException:
    return api_error(404, "target_not_found", f"Table {table!r} doesn't exist in the target database.", field)


def _run_not_found(run_id: str, field: str | None = None) -> HTTPException:
    return api_error(404, "run_not_found",
                     f"Run {run_id} was not found. It may have expired; upload the file again.", field)


def _summaries(db: str) -> list[dict]:
    with closing(sqlite3.connect(db)) as conn:
        return [{"name": t, "row_count": row_count(conn, t),
                 "column_count": len(conn.execute(f"PRAGMA table_info({quote(t)})").fetchall())}
                for t in list_tables(conn)]


@app.get("/api/targets", response_model=list[TargetSummary])
def targets(db: str = Depends(get_target_db)) -> list[dict]:
    """Tables in the target database that a file can be loaded into."""
    return _summaries(db)


@app.get("/api/targets/{table}", response_model=TargetDetail)
def target(table: str, db: str = Depends(get_target_db)) -> dict:
    """A table's definition read back from SQLite: DDL, columns, keys, CHECK constraints, row count."""
    with closing(sqlite3.connect(db)) as conn:
        try:
            return describe_table(conn, table)
        except TargetNotFound:
            raise _target_not_found(table) from None


@app.post("/api/targets/reset", response_model=list[TargetSummary])
def reset_targets(db: str = Depends(get_target_db)) -> list[dict]:
    """Demo helper: recreate the demo customers table with only its seed rows."""
    reset_demo_database(db)
    return _summaries(db)


@app.get("/api/demo/uploads/{file_name}")
def demo_upload(file_name: str) -> FileResponse:
    """Demo files to upload: one that fails validation and its corrected version."""
    if file_name not in DEMO_UPLOAD_FILES:
        raise api_error(404, "file_not_found", f"No demo file named {file_name!r}.")
    return FileResponse(DEMO_UPLOADS_DIR / file_name, media_type="text/csv", filename=file_name)


@app.post("/api/runs", response_model=RunDetail, status_code=201)
def create_run(
    target_table: str = Form(...),
    file: UploadFile = File(...),
    retry_of: str | None = Form(None),
    db: str = Depends(get_target_db),
    runs: RunStore = Depends(get_run_store),
) -> dict:
    """Upload one CSV file and run the pipeline against target_table. A run that fails validation or
    the load is still created (201) with status FAILED; only an unreadable file is an error."""
    with closing(sqlite3.connect(db)) as conn:
        if target_table not in list_tables(conn):
            raise _target_not_found(target_table, "target_table")
    previous = None
    if retry_of:
        record = runs.get(retry_of)
        if record is None:
            raise _run_not_found(retry_of, "retry_of")
        if record.detail["target_table"] != target_table:
            raise api_error(422, "retry_target_mismatch",
                            f"Run {retry_of} loaded into {record.detail['target_table']!r}, not {target_table!r}.",
                            "retry_of")
        previous = record.detail
    try:
        upload = parse_csv(read_limited(file.file))
    except UploadError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail()) from e

    try:
        outcome = run_pipeline(db, target_table, upload, file.filename or "upload.csv", new_run_id(), previous)
    except TargetNotFound:
        raise _target_not_found(target_table, "target_table") from None
    record = RunRecord(outcome.detail, outcome.target, outcome.upload_profile)
    runs.add(record)
    return record.to_api()


@app.get("/api/runs", response_model=list[RunListItem])
def list_runs(runs: RunStore = Depends(get_run_store)) -> list[dict]:
    """Runs kept in memory, newest first."""
    keys = ("run_id", "created_at", "status", "failed_stage", "target_table", "file_name", "retry_of",
            "row_count", "rows_loaded")
    return [{**{k: r.detail[k] for k in keys}, "investigated": r.investigation is not None} for r in runs.list()]


@app.get("/api/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, runs: RunStore = Depends(get_run_store)) -> dict:
    record = runs.get(run_id)
    if record is None:
        raise _run_not_found(run_id)
    return record.to_api()


@app.post("/api/runs/{run_id}/investigate", response_model=InvestigateResponse)
def investigate_upload_run(
    run_id: str,
    runs: RunStore = Depends(get_run_store),
    make_provider: Callable[[], LLMProvider] = Depends(get_llm_provider),
) -> InvestigateResponse:
    """AI investigation of a failed run, from that run's own evidence. The result is also saved on the run."""
    record = runs.get(run_id)
    if record is None:
        raise _run_not_found(run_id)
    if record.detail["status"] != "FAILED":
        raise api_error(409, "run_not_failed", f"Run {run_id} succeeded, so there is no failure to investigate.")
    try:
        provider = make_provider()
    except LLMError as e:
        raise api_error(503, "llm_not_configured", f"LLM not configured: {e}") from e
    try:
        result = investigate_run(record, provider)
    except InvestigationParseError as e:
        log.warning("Unparseable LLM output: %s", e)
        raise api_error(502, "llm_invalid_output", f"LLM returned an invalid investigation: {e}") from e
    except LLMTimeoutError as e:
        log.warning("LLM timed out: %s", e)
        raise api_error(504, "llm_timeout", f"LLM provider timed out: {e}") from e
    except LLMError as e:
        log.warning("LLM call failed: %s", e)
        raise api_error(502, "llm_unavailable", f"LLM provider unavailable: {e}") from e
    except Exception as e:  # never leak a stack trace to the frontend
        log.exception("Run investigation failed unexpectedly")
        raise api_error(500, "internal_error", "Investigation failed due to an internal error.") from e
    response = InvestigateResponse.from_result(result)
    record.investigation = response.model_dump()
    return response
