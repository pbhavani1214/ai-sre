"""FastAPI app.  Run:  uvicorn src.api.main:app --reload --env-file .env"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from typing import Callable

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.ai.provider import LLMError, LLMProvider, LLMTimeoutError, get_provider
from src.api.schemas import (
    DatabaseListResponse,
    DemoRunResponse, DemoScenarioResponse, HealthResponse, InvestigateRequest, InvestigateResponse,
    RunInvestigateResponse, RunSummary, TargetListResponse, TargetSchemaResponse,
)
from src.config import cors_origins, target_db_dir, target_db_path
from src.investigation.models import InvestigationParseError
from src.investigation.service import investigate_pipeline
from src.runs.ingest import UploadError, check_file_type, parse_csv, read_limited
from src.runs.service import INVESTIGABLE, RETRYABLE, execute_run, investigate_run
from src.runs.store import RunRecord, RunStore, new_run_id, store
from src.target.database import initialize_database
from src.target.discovery import discover_schema
from src.target.catalog import Database, DatabaseCatalog, list_tables, target_summary
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


def get_database_catalog(default_db: str = Depends(get_target_db)) -> DatabaseCatalog:
    """FastAPI dependency: the databases a user can choose from (the database folder plus the default database).
    Tests override it, or get_target_db for the default database."""
    return DatabaseCatalog(target_db_dir(), default_db)


def _database(catalog: DatabaseCatalog, database_id: str | None) -> Database:
    database = catalog.resolve(database_id)
    if database is None:
        raise api_error(404, "database_not_found", f"Database '{database_id}' was not found.", "database_id")
    return database


def _target_table(database: Database, target_id: str) -> str:
    """The table named by target_id, if it exists in the database (table names are only ever used after this)."""
    if target_id not in list_tables(database.path):
        raise api_error(404, "target_not_found", f"Target '{target_id}' was not found.", "target_id")
    return target_id


@app.get("/api/databases", response_model=DatabaseListResponse)
def list_databases(catalog: DatabaseCatalog = Depends(get_database_catalog)) -> dict:
    """The SQLite databases a user can choose from: the default database first, then the database folder's files."""
    return {"databases": [d.to_dict() for d in catalog.databases()]}


@app.get("/api/targets", response_model=TargetListResponse, response_model_exclude_none=True)
def list_targets(database_id: str | None = Query(None),
                 catalog: DatabaseCatalog = Depends(get_database_catalog)) -> dict:
    """The tables of one database (the default database when database_id is omitted), discovered from SQLite."""
    database = _database(catalog, database_id)
    return {"targets": [target_summary(database, t) for t in list_tables(database.path)]}


@app.get("/api/targets/{target_id}", response_model=TargetSchemaResponse, response_model_exclude_none=True)
def target_schema(target_id: str, database_id: str | None = Query(None),
                  catalog: DatabaseCatalog = Depends(get_database_catalog)) -> dict:
    """The target's columns and constraints, discovered from its SQLite database."""
    database = _database(catalog, database_id)
    table = _target_table(database, target_id)
    with closing(sqlite3.connect(database.path)) as conn:
        schema = discover_schema(conn, table)
    return {"target_id": table, "table_name": table, "database_type": "sqlite",
            "database_id": database.database_id, **schema}


# --- runs ------------------------------------------------------------------------------------

def get_run_store() -> RunStore:
    """FastAPI dependency: the in-memory run store. Tests override it."""
    return store


def _run_not_found(run_id: str) -> HTTPException:
    return api_error(404, "run_not_found", f"Run '{run_id}' was not found.", "run_id")


def _start_run(database: Database, table: str, file: UploadFile, runs: RunStore,
               parent_run_id: str | None = None) -> dict:
    """Read the file, create the run, validate it and load it if nothing FAILED. An unreadable file creates no run."""
    try:
        check_file_type(file.filename)
        upload = parse_csv(read_limited(file.file))
    except UploadError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail()) from e
    record = RunRecord(run_id=new_run_id(), target_id=table, target_table=table, file_name=file.filename,
                       upload=upload, parent_run_id=parent_run_id, database_id=database.database_id)
    runs.add(record)
    execute_run(record, str(database.path))
    return record.to_summary()


@app.post("/api/runs", response_model=RunSummary, status_code=201)
def create_run(
    target_id: str = Form(...),
    file: UploadFile = File(...),
    database_id: str | None = Form(None),
    runs: RunStore = Depends(get_run_store),
    catalog: DatabaseCatalog = Depends(get_database_catalog),
) -> dict:
    """Upload one CSV for a target (in database_id, or the default database): validate it against the discovered
    schema, then append it to the target in one transaction if no check FAILED."""
    database = _database(catalog, database_id)
    return _start_run(database, _target_table(database, target_id), file, runs)


@app.get("/api/runs/{run_id}", response_model=RunSummary)
def get_run(run_id: str, runs: RunStore = Depends(get_run_store)) -> dict:
    record = runs.get(run_id)
    if record is None:
        raise _run_not_found(run_id)
    return record.to_summary()


@app.post("/api/runs/{run_id}/retry", response_model=RunSummary, status_code=201)
def retry_run(
    run_id: str,
    file: UploadFile = File(...),
    runs: RunStore = Depends(get_run_store),
    catalog: DatabaseCatalog = Depends(get_database_catalog),
) -> dict:
    """Create a NEW run from a corrected CSV for the same target in the same database. The original run is not
    changed."""
    parent = runs.get(run_id)
    if parent is None:
        raise _run_not_found(run_id)
    if parent.status not in RETRYABLE:
        raise api_error(409, "run_not_retryable",
                        f"Run '{run_id}' is {parent.status}; only FAILED_VALIDATION or LOAD_FAILED runs can be retried.",
                        "run_id")
    database = _database(catalog, parent.database_id or None)
    return _start_run(database, _target_table(database, parent.target_table), file, runs, parent_run_id=parent.run_id)


@app.post("/api/runs/{run_id}/investigate", response_model=RunInvestigateResponse)
def investigate_live_run(
    run_id: str,
    runs: RunStore = Depends(get_run_store),
    make_provider: Callable[[], LLMProvider] = Depends(get_llm_provider),
) -> RunInvestigateResponse:
    """AI investigation of a failed run, from that run's stored evidence only. Validation is not re-run and the
    run status doesn't change; the result is saved on the run."""
    record = runs.get(run_id)
    if record is None:
        raise _run_not_found(run_id)
    if record.status not in INVESTIGABLE:
        raise api_error(409, "run_not_investigable",
                        f"Run '{run_id}' is {record.status}; only FAILED_VALIDATION or LOAD_FAILED runs can be "
                        "investigated.", "run_id")
    try:
        provider = make_provider()
    except LLMError as e:
        raise api_error(503, "llm_not_configured", "AI investigation is not configured.") from e
    try:
        result = investigate_run(record, provider)
    except InvestigationParseError as e:
        log.warning("Unparseable LLM output for %s: %s", run_id, e)
        raise api_error(502, "invalid_ai_response", "AI investigation returned an invalid response.") from e
    except LLMTimeoutError as e:
        log.warning("LLM timed out for %s: %s", run_id, e)
        raise api_error(504, "llm_timeout", "AI investigation timed out.") from e
    except LLMError as e:
        log.warning("LLM call failed for %s: %s", run_id, e)
        raise api_error(502, "llm_provider_error", "The AI provider could not complete the investigation.") from e
    except Exception as e:  # never leak a stack trace to the frontend
        log.exception("Run investigation failed unexpectedly")
        raise api_error(500, "internal_error", "Investigation failed due to an internal error.") from e
    response = RunInvestigateResponse(run_id=record.run_id, **InvestigateResponse.from_result(result).model_dump())
    record.investigation = response.model_dump()
    return response
