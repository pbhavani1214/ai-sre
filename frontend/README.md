# Frontend: AI Reliability Engineer

React + Vite + [Mantine](https://mantine.dev) UI for loading a CSV into an existing target table, investigating
failures with AI, and retrying with a corrected file.

## Run

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm run dev            # http://localhost:5173
npm test               # Vitest + Testing Library
npm run build          # production build in dist/
```

Start the backend first (see the root README). The app always needs it: there is no offline or sample-data mode.
The header badge shows the connection: **Backend connected**, **AI not configured** (backend up, no
`LLM_API_KEY`), **Backend offline**, or **No backend configured** (`VITE_API_BASE_URL` not set).

## User flow

1. **Target selection**: pick a database (every SQLite file in the backend's database folder), then a table in it;
   the table's columns and constraints come from the API.
2. **Upload**: one CSV (up to 10 MB). The browser only checks the `.csv` name and size; the backend validates.
3. **Run result**:
   - `FAILED_VALIDATION`: summary counts and every check with its evidence, then **Investigate with AI**: the root
     cause with the failures grouped by likely cause, **Fix this file** (row-by-row suggested changes checked against
     the file, with **Download suggested CSV** and **Retry with suggested CSV**), **Prevent it next time**, then
     hypotheses, a regression test generated from the table's schema, the trace and the evidence reviewed. Then
     **Fix the data and retry** (upload a corrected CSV as a new run linked to this one).
   - `SUCCEEDED`: the load result as returned by the backend. `LOAD_FAILED`: validation passed but the load was
     rolled back; investigate and retry are available.
   - A retry shows its parent run, and **View original run** returns to it unchanged.

Light and dark mode follow the OS and can be toggled from the header. The layout works down to phone width.

## Structure

```
src/
├── main.jsx, App.jsx, theme.js, styles.css, utils.js
├── pages/          TargetSelectionPage, UploadPage, RunResultPage
├── components/     TargetSchema, CsvDrop, RunValidationResults, RunInvestigationPanel, InvestigationResult,
│                   SuggestedFixes, HypothesisList, CitedList, CodeBlock, RetryPanel, AppHeader
├── hooks/          useTargets, useHealth
├── services/       api.js (the only module that calls the backend), errors.js (error codes -> messages)
├── types/index.js  JSDoc shapes of the API payloads
└── test/           test setup and helpers
```

## Backend contract

`docs/implementation/CONTRACT.md` is the source of truth. Endpoints used:

| Method | Path | Used for |
|---|---|---|
| `GET` | `/health` | Header connection badge |
| `GET` | `/api/databases` | Database dropdown |
| `GET` | `/api/targets?database_id=` | Table dropdown for the chosen database |
| `GET` | `/api/targets/{target_id}?database_id=` | Schema and constraints |
| `POST` | `/api/runs` | Upload one CSV (`target_id`, `file`, `database_id`) and get the validated run |
| `GET` | `/api/runs/{run_id}` | Open a retry's parent run |
| `POST` | `/api/runs/{run_id}/investigate` | AI investigation of a failed run |
| `GET` | `/api/runs/{run_id}/suggested-csv` | The upload with the investigation's fixes applied (download or retry) |
| `POST` | `/api/runs/{run_id}/retry` | Corrected CSV (`file`) as a new run with `parent_run_id` |

Errors use `{detail: {code, message, field}}`; `api.js` turns them into an `ApiError`, and `errors.js` maps codes to
the messages shown.
