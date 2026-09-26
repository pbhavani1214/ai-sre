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
| `src/target/` | SQLite target database (`database.py`, seeded `customer` table; `python -m src.target.database [--reset]`), target registry (`registry.py`) and schema discovery from SQLite (`discovery.py`) |
| `src/runs/` | Upload runs: CSV envelope checks (`ingest.py`), in-memory run store with the latest 20 runs (`store.py`), target-aware validation derived from the discovered schema (`validation.py`), and the run lifecycle: validation, transactional APPEND load, run-scoped AI investigation evidence (`service.py`) |
| `data/demo_uploads/` | `customer_bad.csv` (fails 5 checks) and `customer_fixed.csv` (passes all 7 and loads 7 rows) for the `customer` target; reset the target with `python -m src.target.database --reset` |
| `src/api/` | FastAPI app: `/health`, `/api/demo/scenario`, `/api/demo/run`, `/api/investigate`, `/api/targets`, `/api/targets/{target_id}`, `POST /api/runs`, `GET /api/runs/{run_id}`, `POST /api/runs/{run_id}/investigate`, `POST /api/runs/{run_id}/retry` |
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
