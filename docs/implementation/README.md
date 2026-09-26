# Implementation plan and process

Two Claude Code sessions build this app in parallel: a **frontend (FE) session** and a **backend (BE)
session**. This folder keeps them in sync. Read this file before starting any work.

## The goal

Let a user upload their own source and target CSV files (plus an optional pipeline run log), check them
with deterministic validations, and have the AI investigate what went wrong. The bundled demo stays
available as a "Try the demo" option.

## Phases

| Phase | Goal | Status |
|---|---|---|
| 0. Setup | This folder, the API contract, and the Phase 1 instructions | Done |
| 1. Upload | Upload the source CSV, the target CSV and an optional run log; preview them | Ready to start |
| 2. Column mapping and checks on any CSV | Map the key and optional columns; run checks on uploaded data | Not started |
| 3. AI on uploaded data | Investigate an uploaded run with the AI | Not started |
| 4. Finishing | Large-file limits, a consistent error format, tests, one-command start, demo walkthrough | Not started |

The FE session writes the detailed instructions for a phase at its start (see "How a phase runs"),
because each phase builds on what the previous one produced. Phases 2 to 4 above are outlines until then.

### Decisions already made
- The pipeline run file is **optional**. Without one, the Pipeline steps and Logs views are hidden and the AI
  works from the data checks only.
- Uploaded runs are stored **in memory** in the backend. They are lost when the backend restarts.
- Upload limits: **10 MB and 50,000 data rows per CSV file**, **1 MB** for the run log.
- The bundled demo stays, behind a **Try the demo** option.
- The code stays in its current layout (`src/`, `tests/`, `frontend/`). Moving it into `backend/` is out
  of scope, because it would touch every file and cause merge conflicts between the sessions.

## Who owns what

| Path | Owner | Notes |
|---|---|---|
| `src/`, `tests/`, `data/`, `requirements.txt`, `example_usage.py`, root `.env.example` | BE session | |
| `frontend/` | FE session | |
| `docs/implementation/` | FE session | The BE session only fills in the "Completion report" section of its own phase file |
| Root `README.md` | Shared | BE edits the backend and run sections; FE edits the frontend sections |
| `CLAUDE.md` | FE session | |

Never edit files the other session owns. If you need a change there, write it under "Questions for the other
session" in your phase file and stop working on that item.

## The API contract

[`CONTRACT.md`](CONTRACT.md) is the single source of truth for every endpoint, request, response and error.
- Only the FE session changes it, and only between phases.
- The BE session implements it exactly: same paths, field names, types, status codes and error codes.
  If something in it is wrong or impossible, don't improvise. Write it under "Questions for the other
  session" in your phase file, implement everything else, and report it in the completion report.
- The FE session builds against the examples in the contract, so both sessions can work at the same time.

## How a phase runs

1. **Start.** The FE session writes `phase-N/BE.md` and `phase-N/FE.md`, updates `CONTRACT.md`, and
   merges these docs into `main`.
2. **Sync.** Both sessions pull the latest `main`, then each creates its own working branch from it.
3. **Build.** Each session follows its own instruction file only, runs the checks listed there, and pushes.
4. **Merge the backend first.** The BE pull request merges into `main` first. The FE session then brings
   `main` into its branch, tests against the real backend, and its pull request merges second.
5. **Close.** The FE session marks the phase Done in the table above, and both sessions pull `main` again
   before the next phase.

## Definition of done (every phase)

- Backend: `python -m pytest -q` passes, and every new endpoint has tests for its success and error cases.
- Frontend: `npm run build` succeeds, and the flow works against the real backend in a browser.
- The existing demo flow still works.
- The phase file's checklist is complete, and its "Completion report" section is filled in, including
  anything not done and why.
