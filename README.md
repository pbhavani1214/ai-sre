# AI Software Reliability Engineer

Load a CSV file into an existing SQLite table safely. The backend validates every row against the table's real
schema and constraints before anything is written. When a file fails, an AI investigation explains why the values
are wrong, suggests row-by-row fixes, and recommends how to prevent it next time. You then retry with a corrected
file.

```
Choose a database and table → upload a CSV → deterministic validation
      ├─ passes → rows appended in one transaction (SUCCEEDED)
      └─ fails  → AI investigation → fix the file (or use the suggested CSV) → retry as a new linked run
```

Validation is deterministic: the facts come from code, not from the AI. The AI only interprets those facts. The
system never runs AI-generated code and never lets the AI write to the database.

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
  - [Ubuntu / Linux](#ubuntu--linux)
  - [macOS](#macos)
  - [Windows](#windows)
- [Configuration](#configuration)
- [Try the application](#try-the-application)
- [Run the tests](#run-the-tests)
- [Databases](#databases)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)

## Features

- **Database and table selection.** Every SQLite file in a folder is listed, and every table in it can be chosen.
  Columns and constraints are discovered from SQLite itself; nothing is hardcoded.
- **Upload validation.** One CSV (UTF-8, header row, up to 10 MB) is checked for:
  - required columns and unexpected columns
  - column types
  - NOT NULL
  - PRIMARY KEY and UNIQUE duplicates, both within the file and against rows already in the table
  - CHECK constraints (allowed values)

  Every failure names the file row and value.
- **All-or-nothing load.** If no check fails, the rows are appended in one transaction. On a database error the load
  is rolled back and nothing is written.
- **AI investigation** of a failed run:
  - **Root cause.** The likely origin of the bad values, with the failures grouped by cause.
  - **Fix this file.** Row-by-row suggestions (replace, delete row, or decide yourself), checked by the backend
    against your file. Download the suggested CSV, or retry with it directly.
  - **Prevent it next time.** Steps for whoever produces the file.
  - **Supporting detail.** Hypotheses marked supported or rejected, the evidence the AI reviewed, and a trace of
    the investigation steps. The AI must cite evidence IDs, and the backend flags citations it can't match.
  - **Regression test.** A reusable pytest data check for the table, generated from its schema (not by the AI).
- **Retry.** Upload a corrected file as a new run linked to the failed one; the original run stays unchanged.
- **Light and dark mode.** The layout works on desktop and phone.

## Tech stack

| Part | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, pandas, SQLite (standard library `sqlite3`) |
| AI | OpenAI or Anthropic over plain HTTP (no SDK), chosen with environment variables |
| Frontend | React 19, Vite 8, Mantine 9 |
| Tests | pytest (backend), Vitest and Testing Library (frontend) |

## Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Python | 3.11 or newer | `python3 --version` (Windows: `py --version`) |
| Node.js | 20.19+ or 22.12+ (required by Vite 8) | `node --version` |
| npm | comes with Node.js | `npm --version` |
| Git | any recent version | `git --version` |
| LLM API key | OpenAI or Anthropic | only needed for the AI investigation |

Everything except the AI investigation works without an API key.

## Quick start

Run all commands from the repository root (the folder that contains `src/`, `frontend/` and this README) unless a
step says `cd frontend`. You need **two terminals**: one for the backend, one for the frontend.

### Ubuntu / Linux

Install the prerequisites, if needed:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
# Node.js 22 (NodeSource); or use nvm: https://github.com/nvm-sh/nvm
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

**Terminal 1: backend** (http://localhost:8000)

```bash
git clone https://github.com/sandeep-sakilam/ai-sre.git
cd ai-sre
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then edit .env: set LLM_PROVIDER, LLM_API_KEY, LLM_MODEL
uvicorn src.api.main:app --reload --env-file .env
```

**Terminal 2: frontend** (http://localhost:5173)

```bash
cd ai-sre/frontend
npm install
cp .env.example .env            # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173.

### macOS

Install the prerequisites, if needed, with [Homebrew](https://brew.sh):

```bash
brew install python@3.12 node git
```

The backend and frontend steps are the same as on Ubuntu:

```bash
# Terminal 1: backend
git clone https://github.com/sandeep-sakilam/ai-sre.git
cd ai-sre
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then edit .env
uvicorn src.api.main:app --reload --env-file .env

# Terminal 2: frontend
cd ai-sre/frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173.

### Windows

Install the prerequisites, if needed:

- Python 3.11+ from https://www.python.org/downloads/. Tick **Add python.exe to PATH** during setup.
- Node.js LTS from https://nodejs.org.
- Git from https://git-scm.com.

Or, with winget:

```powershell
winget install Python.Python.3.12 OpenJS.NodeJS.LTS Git.Git
```

**Terminal 1: backend** (PowerShell)

```powershell
git clone https://github.com/sandeep-sakilam/ai-sre.git
cd ai-sre
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # then edit .env, e.g. notepad .env
uvicorn src.api.main:app --reload --env-file .env
```

If PowerShell says running scripts is disabled, allow scripts for your user once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

In Command Prompt (cmd.exe), activate with `.venv\Scripts\activate.bat` and copy with
`copy .env.example .env`.

**Terminal 2: frontend** (PowerShell)

```powershell
cd ai-sre\frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open http://localhost:5173.

### Check that it works

- The header badge reads **Backend connected**. It reads **AI not configured** when `LLM_API_KEY` is empty, and
  **Backend offline** when the backend isn't running.
- http://localhost:8000/health returns `"llm_configured": true` and your provider and model.
- http://localhost:8000/docs shows the interactive API documentation.

To stop either server, press `Ctrl+C` in its terminal. The next time, only re-activate the virtual environment and
run `uvicorn ...` (backend) and `npm run dev` (frontend); the installs are not needed again.

## Configuration

### Backend: `.env` in the repository root

Copy it from `.env.example`. It is git-ignored: never commit a real key.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `openai` or `anthropic` |
| `LLM_API_KEY` | (empty) | Your API key. Without it, everything except the AI investigation works. |
| `LLM_MODEL` | `gpt-4o` / `claude-sonnet-5` | The model. Prefer a full-size model; small models (for example `gpt-4o-mini`) tend to restate validation instead of explaining it. |
| `LLM_BASE_URL` | provider default | Optional, for an OpenAI-compatible endpoint |
| `LLM_TIMEOUT` | `120` | Seconds to wait for the AI. Raise it for slower (reasoning) models. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API |
| `TARGET_DB_DIR` | `data/databases` | Folder whose SQLite files are listed as databases |
| `TARGET_DB_PATH` | `TARGET_DB_DIR/crm.db` | Optional: the default database. Leave it unset unless you need it. |

Restart the backend after changing `.env`.

Example with OpenAI:

```
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
```

### Frontend: `frontend/.env`

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000`. It must be set; the app always needs the backend. |

Restart `npm run dev` after changing it.

## Try the application

Sample files are in `data/demo_uploads/`. The demo databases are created automatically the first time the backend
lists databases.

| Database → table | Failing file | What fails | Corrected file |
|---|---|---|---|
| CRM (`crm.db`) → Customer | `customer_bad.csv` | 5 checks: a prefixed ID, an empty name, a duplicate ID, a duplicate e-mail, two disallowed statuses | `customer_fixed.csv` (loads 7 rows) |
| Sales (`sales.db`) → Orders | `orders_bad.csv` | 4 checks | `orders_fixed.csv` (loads 6 rows) |

Walkthrough:

1. Open http://localhost:5173. Choose **CRM (crm.db)**, then the **Customer** table. Its columns and constraints
   are shown. Click **Continue**.
2. Upload `data/demo_uploads/customer_bad.csv` and click **Create run**. The run is **Failed validation**, and every
   failed check lists the rows and values involved. Nothing was written to the table.
3. Click **Investigate with AI** (takes up to about a minute). Review:
   - the root cause and its likely causes
   - **Fix this file**
   - **Prevent it next time**
   - the tabs: Hypotheses, Regression test, Trace, Evidence reviewed
4. Optional: click **Retry with suggested CSV**. The suggested fixes are applied and the file is validated again. It
   still fails, because some values need your decision, such as the empty name.
5. Under **Fix the data and retry**, upload `data/demo_uploads/customer_fixed.csv`. The new run is **Succeeded**
   with 7 rows loaded, and it links back to the failed run.
6. Try the same with **Sales (sales.db) → Orders**, using `orders_bad.csv`, then `orders_fixed.csv`.

A corrected file can only be loaded once. Loading it again fails with "already exists in the target table", which
is correct: those keys are now in the table. [Reset the databases](#reset-the-demo-databases) to repeat the demo.

## Run the tests

Backend, from the repository root with the virtual environment active:

```bash
python -m pytest -q
```

The tests use temporary databases and a stub AI provider. They need no API key and never touch `data/databases`.

Frontend:

```bash
cd frontend
npm test            # Vitest + Testing Library
npm run build       # production build in frontend/dist
```

On Windows, use the same commands in PowerShell, with `py` instead of `python` if `python` isn't on your PATH.

## Databases

### Reset the demo databases

From the **repository root** (not from `data/` or `frontend/`):

```bash
python -m src.target.database --reset        # macOS / Ubuntu: python3 works too
```

```powershell
py -m src.target.database --reset            # Windows
```

This recreates the demo tables in `crm.db` and `sales.db` from their original rows: `customer` (10 rows),
`orders` (5) and `products` (3). Other databases in the folder are not touched. The command doesn't read `.env`; if
you changed `TARGET_DB_DIR`, set it in the terminal first (`TARGET_DB_DIR=path python -m ...` on macOS/Linux,
`$env:TARGET_DB_DIR="path"` on PowerShell).

You can also delete `data/databases/crm.db` and `sales.db`; the backend recreates them with the original rows.

### Use your own database

Copy any SQLite file (`.db`, `.sqlite` or `.sqlite3`) into `data/databases/`, or into your `TARGET_DB_DIR`. Refresh
the page, and it appears in the database list with all its tables. Only single-column `column IN ('a', 'b')` CHECK
constraints are evaluated; other CHECK constraints are listed but not validated. Database files are git-ignored.

## API reference

The full, interactive documentation is at http://localhost:8000/docs while the backend runs.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Status, and whether the AI is configured (provider, model) |
| `GET` | `/api/databases` | The databases to choose from |
| `GET` | `/api/targets?database_id=` | The tables of a database |
| `GET` | `/api/targets/{target_id}?database_id=` | A table's columns and constraints |
| `POST` | `/api/runs` | Multipart form: `target_id`, `file`, optional `database_id`. Validates and, if nothing fails, loads. |
| `GET` | `/api/runs/{run_id}` | A run and its results |
| `POST` | `/api/runs/{run_id}/investigate` | AI investigation of a failed run |
| `GET` | `/api/runs/{run_id}/suggested-csv` | The uploaded file with the investigation's fixes applied |
| `POST` | `/api/runs/{run_id}/retry` | Multipart form: `file`. A corrected file as a new run linked to the failed one. |

Run statuses: `FAILED_VALIDATION`, `SUCCEEDED` or `LOAD_FAILED`. Errors look like
`{"detail": {"code": "...", "message": "...", "field": "..."}}`.

The earlier pipeline demo API (`/api/demo/scenario`, `/api/demo/run`, `/api/investigate`, with the files in `data/`
and `example_usage.py`) is still available, but the UI doesn't use it.

## Project structure

```
ai-sre/
├── src/
│   ├── api/            FastAPI app (main.py) and request/response models (schemas.py)
│   ├── target/         demo databases (database.py), database catalog (catalog.py), schema discovery (discovery.py)
│   ├── runs/           CSV checks (ingest.py), validation (validation.py), run store (store.py),
│   │                   run lifecycle and AI evidence (service.py), fixes and profiles (insights.py),
│   │                   generated regression test (regression.py)
│   ├── investigation/  LLM prompt, citation checks and structured result
│   ├── ai/             OpenAI / Anthropic provider
│   ├── validation/     checks for the earlier pipeline demo
│   └── data/           the earlier pipeline demo scenario
├── tests/              backend tests (pytest)
├── data/
│   ├── demo_uploads/   sample CSV files
│   └── databases/      SQLite databases (created at runtime, git-ignored)
├── frontend/           React UI (see frontend/README.md)
├── .env.example        backend configuration template
└── requirements.txt
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'src'` | Run the command from the repository root, not from `data/` or `frontend/`. |
| `uvicorn: command not found`, or `No module named fastapi` | Activate the virtual environment first (`source .venv/bin/activate`, or `.venv\Scripts\Activate.ps1` on Windows). |
| `python: command not found` (Ubuntu/macOS) | Use `python3`. Inside an active virtual environment, `python` works. |
| `ensurepip is not available` (Ubuntu) | `sudo apt install python3-venv`, then create the virtual environment again. |
| PowerShell: "running scripts is disabled" | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Badge shows **Backend offline** | Start the backend. Check that `VITE_API_BASE_URL` in `frontend/.env` is `http://localhost:8000`, then restart `npm run dev`. |
| Badge shows **No backend configured** | Create `frontend/.env` from `frontend/.env.example`, then restart `npm run dev`. |
| Badge shows **AI not configured** | Set `LLM_API_KEY` in the root `.env` and restart the backend. |
| The AI investigation fails with a provider error | Check the key, the model name and your account's credit; the backend terminal shows the provider's message. For slow models, raise `LLM_TIMEOUT`. |
| CORS error in the browser console | Open the app at http://localhost:5173, or add your origin to `CORS_ORIGINS`. |
| Port 8000 or 5173 is in use | Stop the other process, or use `uvicorn ... --port 8001` (then update `VITE_API_BASE_URL`); Vite picks the next free port by itself (add that origin to `CORS_ORIGINS`). |
| An extra "Target" database appears | Remove an old `TARGET_DB_PATH=data/target.db` line from `.env`. |
| "already exists in the target table" when loading a corrected file | It was already loaded. [Reset the demo databases](#reset-the-demo-databases). |
| "Run ... was not found" after a backend restart | Runs are kept in memory only; upload the file again. |

## Limitations

This is a prototype:

- **Runs live in memory.** The latest 20 are kept, and all are lost when the backend restarts. Loaded rows stay in
  the database.
- **Load behaviour is fixed.** Loads only append rows; there is no update or upsert. Files are limited to 10 MB.
- **The AI can miss things.** Its answers can vary from run to run and can miss a suggestion; re-run the
  investigation if something looks incomplete. Suggestions are never applied without your action, and a corrected
  file is always validated again.
- **No authentication.** Run it locally only.
