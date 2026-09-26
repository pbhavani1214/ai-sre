# AI Software Reliability Engineer

Load a CSV into an existing SQLite table: deterministic validation against the discovered schema, an AI
investigation of failures, and retry with a corrected file. See README.md for the full description.

## Commands
- Backend (from the repo root): `pip install -r requirements.txt`, `python -m pytest -q`,
  `uvicorn src.api.main:app --reload --env-file .env` (serves http://localhost:8000)
- Frontend: `cd frontend && npm install`, `npm test`, `npm run build`, `npm run dev` (serves http://localhost:5173)
- Reset the demo databases: `python -m src.target.database --reset`

## Rules
- Never commit real keys; `.env` is git-ignored.
- Keep the API in `src/api/schemas.py`, `frontend/src/services/api.js` and the README's API reference in sync.
