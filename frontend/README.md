# Frontend: AI Reliability Engineer

React + Vite + [Mantine](https://mantine.dev) UI for investigating a failed data pipeline run.

## Run

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # production build in dist/
```

With no configuration the UI runs on **bundled demo data**, so no backend is needed. The header shows a
"Demo data" badge in this mode. To use a real backend, copy `.env.example` to `.env` and set
`VITE_API_BASE_URL` (for example `http://localhost:8000`).

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

## Backend contract (proposed)

The UI expects two endpoints. Payloads mirror the existing Python models, so the backend can return
`ValidationResult.to_dict()` and `InvestigationResult.to_dict()` directly.

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/scenario` | `{ pipeline_description, source: [...rows], target: [...rows], pipeline_run, validation_results: [ValidationResult] }` |
| `POST` | `/api/investigations` | `InvestigationResult` (`summary`, `hypotheses`, `evidence`, `root_cause`, `recommended_fix`, `regression_test`) |

## Demo data

- `src/data/scenario.json` is produced from the real backend code (`load_scenario()` and
  `run_all_validations()`), so the counts and check results are exactly what the backend computes.
- `src/data/investigation.mock.json` is a hand-written, illustrative AI result in the
  `InvestigationResult` shape. It is not real model output.
