# AI Software Reliability Engineer

Two Claude Code sessions build this repo in parallel: a frontend (FE) session and a backend (BE) session.
Work is split into phases.

**Before any change, read [`docs/implementation/README.md`](docs/implementation/README.md).** It covers the
phases, file ownership, and how the sessions stay in sync. Then work only from your own phase file:

- BE session: `docs/implementation/phase-N/BE.md`
- FE session: `docs/implementation/phase-N/FE.md`

Rules that matter most:
- [`docs/implementation/CONTRACT.md`](docs/implementation/CONTRACT.md) is the single source of truth for the
  API. The backend implements it exactly. Only the FE session changes it, and only between phases.
- Don't edit files the other session owns. Put open questions in your phase file under
  "Questions for the other session".
- The backend pull request merges into `main` before the frontend pull request of the same phase.

## Commands
- Backend: `pip install -r requirements.txt`, `python -m pytest -q`,
  `uvicorn src.api.main:app --reload --env-file .env` (serves http://localhost:8000)
- Frontend: `cd frontend && npm install`, `npm run build`, `npm run dev` (serves http://localhost:5173)
