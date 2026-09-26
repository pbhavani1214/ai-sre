# Frontend: AI Reliability Engineer

React + Vite + [Mantine](https://mantine.dev) UI for investigating a failed data pipeline run.

## Run

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # production build in dist/
```

To talk to the FastAPI backend, copy `.env.example` to `.env` (it points at `http://localhost:8000`) and start
the backend first (see the root README). The header badge shows the connection: **Backend connected**,
**AI not configured** (backend up, no `LLM_API_KEY`), or **Backend offline**.

With `VITE_API_BASE_URL` empty the UI runs on **bundled sample data** with no backend, and the header shows a
"Demo data" badge.

## User flow

One page, top to bottom:

1. **Run overview**: the pipeline reported `SUCCESS`, but the data checks disagree. Key numbers are shown
   (source/target rows, missing, duplicates) with a single primary action: **Investigate with AI**.
2. **AI investigation**: idle → running (progress and elapsed time) → result: summary, root cause,
   recommended fix, hypotheses with status and confidence, cited evidence, and a copyable regression test.
   Failures show a retry. The result can be downloaded as JSON.
3. **Evidence**: the deterministic facts, in tabs: data checks (expandable details), pipeline steps
   (row-count changes flagged), logs (filter to warnings and errors), and a source/target data table with
   per-row issue badges and an "only rows with issues" filter.

Light and dark mode follow the OS and can be toggled from the header. The layout is responsive down to
phone width.

## Structure

```
src/
├── main.jsx, App.jsx, theme.js, styles.css
├── pages/InvestigationPage.jsx      page composition and loading/error states
├── components/                      RunOverview, InvestigationPanel, HypothesisList, EvidenceTabs,
│                                    ValidationChecks, PipelineSteps, LogViewer, DataCompare, CodeBlock
├── hooks/                           useScenario, useInvestigation
├── services/api.js                  the only module that talks to the backend (or the mocks)
├── types/index.js                   JSDoc shapes of the API payloads
└── data/                            demo data (see below)
```

## Backend contract

`src/services/api.js` is the only module that calls the backend. Shapes are documented in `src/types/index.js`
and defined by the Pydantic models in `src/api/schemas.py`.

| Method | Path | Used for |
|---|---|---|
| `GET` | `/health` | Header connection badge; warns before investigating if no LLM key is set |
| `GET` | `/api/demo/scenario` | Run overview and data checks: pipeline name, execution summary, `validation_results` |
| `GET` | `/api/demo/run` | Pipeline steps, logs and the data table: `pipeline_run`, `source`, `target` rows |
| `POST` | `/api/investigate` | The AI investigation. Sent with `use_demo_data: true`, so the backend re-runs the same checks |

## Demo data

- `src/data/scenario.json` is the backend's `/api/demo/scenario` and `/api/demo/run` responses merged, so the
  counts and check results are exactly what the backend computes. Regenerate it from the repo root after
  backend changes:

  ```bash
  python -c "import json; from src.validation.suite import get_demo_scenario, get_demo_run; \
  json.dump({**get_demo_scenario(), **get_demo_run()}, open('frontend/src/data/scenario.json', 'w'), indent=2)"
  ```
- `src/data/investigation.mock.json` is a hand-written, illustrative AI result in the `/api/investigate`
  response shape. It is not real model output.
