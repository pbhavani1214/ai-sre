# AI Software Reliability Engineer

A 4-hour buildathon prototype. An AI engineer investigates a failed data pipeline
using real data and execution evidence, not guesswork.

## The problem

Data pipelines often "succeed" while quietly corrupting data. Rows get dropped by a
join, duplicated by a retry, or nulled by a type cast, and the run still reports
`SUCCESS`. Engineers then spend hours comparing source and target, reading logs, and
guessing at causes.

## Prototype concept

One demo journey:

```
Broken customer data pipeline
        ↓
Actual validation evidence      (deterministic pandas checks)
        ↓
AI investigation                (LLM reasons over the evidence)
        ↓
Hypotheses → evidence-based root cause → recommended fix → regression test
```

The validation results are deterministic and the AI analysis is dynamic. No
conclusion is hardcoded. The system does not execute generated code.

The demo scenario is a nightly customer sync that reports `SUCCESS` but has several
injected defects. The target has 23 rows against 20 in the source: 3 customers are
missing, but 5 duplicate rows hide the gap.

## Current backend components

| Path | Purpose |
|---|---|
| `src/data/scenario.py` | Generates the broken pipeline scenario (`python -m src.data.scenario`) and loads it |
| `data/` | `source_customers.csv`, `target_customers.csv`, `pipeline_run.json` (config, steps, logs) |
| `src/validation/tools.py` | Record count, null `customer_id`, duplicate `customer_id`, missing target records, invalid email |
| `src/ai/provider.py` | Minimal LLM provider interface (Anthropic / OpenAI over plain HTTP), set by env vars |
| `src/investigation/models.py` | Structured result: summary, hypotheses, evidence, root cause, fix, regression test |
| `src/investigation/service.py` | Builds the evidence, sends it to the LLM, parses structured JSON output |
| `tests/test_validation.py` | Proves the validation tools work, plus the investigation wiring (stub LLM) |
| `src/target/` | The SQLite target database: demo `customers` table (`python -m src.target.demo`) and reading any table's DDL, columns, keys and CHECK constraints back from SQLite |
| `src/runs/` | Upload runs: read the CSV (`ingest.py`), run parse → schema_check → validate → load against the target table (`pipeline.py`), keep runs in memory (`store.py`), build the AI evidence for a failed run (`investigate.py`) |
| `data/demo_uploads/` | `customers_upload_bad.csv` (fails 6 checks) and `customers_upload_fixed.csv` (its corrected version, loads 10 rows) |
| `src/api/` | FastAPI app: `/health`, the demo endpoints, `/api/investigate`, and the upload-run endpoints below |
| `frontend/` | React + Vite + Mantine UI (see `frontend/README.md`) |
| `example_usage.py` | How another module calls the investigation service |

### Run

```bash
pip install -r requirements.txt
python -m pytest -q

# LLM configuration (env vars)
LLM_PROVIDER=anthropic   # or openai
LLM_API_KEY=...
LLM_MODEL=...            # optional
python example_usage.py
```

### Run the full app locally (backend + frontend)

Needs Python 3.11+ and Node 20+. Use two terminals.

```bash
# Terminal 1: backend on http://localhost:8000 (API docs at /docs)
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then set LLM_API_KEY
uvicorn src.api.main:app --reload --env-file .env

# Terminal 2: frontend on http://localhost:5173
cd frontend
npm install
cp .env.example .env                                  # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173. The header badge should read **Backend connected**. Without `LLM_API_KEY` it reads
**AI not configured**: the evidence still loads, but "Investigate with AI" returns an error. The backend only
accepts browser calls from the origins in `CORS_ORIGINS` (the Vite dev server by default).

## Upload runs: one file → existing SQLite table → validate → load or fail → AI

The user uploads one CSV file for an existing table in the target SQLite database
(`TARGET_DB_PATH`, default `data/target.db`, created with the demo `customers` table if missing).

1. **parse**: UTF-8 CSV, every value read as text, empty cells are null. An unreadable file
   (over 10 MB, over 50,000 rows, not UTF-8, bad header, ragged rows) is rejected with an error and creates no run.
2. **schema_check**: file columns against the table's columns (missing required columns, unknown columns).
3. **validate**: every rule comes from the table definition read back from SQLite: NOT NULL, column
   types, PRIMARY KEY and UNIQUE keys (duplicates in the file and conflicts with rows already in the table),
   and every CHECK constraint in the DDL, which SQLite itself evaluates on a TEMP copy of the upload.
4. **load**: only if every check passed, all rows in one transaction. A database error (for example a
   foreign key) rolls back and fails the run at `load`.

A run that fails is still a run (`201`, `status: "FAILED"`) with its validation results, per-row issues
(file line numbers), stage log and row counts. `POST /api/runs/{id}/investigate` sends exactly that
evidence, with the table's DDL, to the same investigation service as the demo. Uploading the corrected
file with `retry_of` links the runs and reports which checks were resolved.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/targets` | Tables that a file can be loaded into, with row counts |
| `GET` | `/api/targets/{table}` | DDL, columns, keys, CHECK constraints, row count, 3 sample rows |
| `POST` | `/api/targets/reset` | Demo helper: recreate the `customers` table with its 10 seed rows |
| `GET` | `/api/demo/uploads/{file}` | Download `customers_upload_bad.csv` or `customers_upload_fixed.csv` |
| `POST` | `/api/runs` | Multipart: `target_table`, `file`, optional `retry_of`. Returns `201` and the run |
| `GET` | `/api/runs` | Runs in memory (last 50), newest first |
| `GET` | `/api/runs/{run_id}` | One run, including its saved investigation |
| `POST` | `/api/runs/{run_id}/investigate` | AI investigation of a failed run (`409` if the run succeeded) |

Errors from these endpoints use `{"detail": {"code", "message", "field"}}`; a missing form field is
FastAPI's default `422`. Pydantic models: `src/api/schemas.py` (`RunDetail`, `TargetDetail`, …).

Demo from the command line (backend running):

```bash
curl -s -X POST localhost:8000/api/targets/reset
curl -s -F target_table=customers -F file=@data/demo_uploads/customers_upload_bad.csv localhost:8000/api/runs    # FAILED
curl -s -X POST localhost:8000/api/runs/<run_id>/investigate                                                      # needs LLM_API_KEY
curl -s -F target_table=customers -F retry_of=<run_id> -F file=@data/demo_uploads/customers_upload_fixed.csv localhost:8000/api/runs   # SUCCESS, 10 rows
```

## Intended architecture (React + FastAPI)

The code will be split so that two developers can work in parallel:

```
ai-software-reliability-engineer/
├── frontend/   React + Vite (JavaScript, CSS)          ← Developer 2
│   └── src/{components,pages,services,hooks,types,data}
├── backend/    Python + FastAPI + pandas (+ SQLite)    ← Developer 1
│   ├── app/{api,ai,investigation,validation,models,services,tools,config}
│   ├── data/{source,target}
│   └── tests/
└── docs/       architecture.md, demo-scenario.md
```

The frontend talks to the backend only through a small JSON HTTP API (e.g. scenario,
validation results, investigation result). The existing `src/` modules will move
under `backend/app/` in a later step. They have not been moved yet.

Out of scope: authentication, RBAC, multi-cloud, multiple database connectors, agent
frameworks (LangChain/CrewAI), and a full ETL platform.
