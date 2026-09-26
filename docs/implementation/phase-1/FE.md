# Phase 1: Frontend instructions (uploads)

For the **FE session**. Read [`../README.md`](../README.md) and the "Phase 1: uploads" section of
[`../CONTRACT.md`](../CONTRACT.md) first.

## Goal

The user starts on a choice between **Upload your data** and **Try the demo**. Uploading takes a source CSV,
a target CSV and an optional run log, shows clear errors, and ends on a preview of what was uploaded. The
demo flow works exactly as it does today.

## Before you start

1. Pull the latest `main` and create your working branch from it.
2. Confirm the baseline: `cd frontend && npm ci && npm run build`.
3. Only touch `frontend/`, `docs/implementation/`, `CLAUDE.md`, and the frontend sections of the root `README.md`.

## Tasks

### 1. Start screen
- New `StartPage` with two cards:
  - **Upload your data**: goes to the upload form.
  - **Try the demo**: goes to the existing `InvestigationPage`, unchanged.
- In sample-data mode (no `VITE_API_BASE_URL`), disable the upload card with the note "Needs the backend".
  The demo card still works.
- Navigate with simple view state in `App.jsx`. Don't add a router; there are only a few screens.
  Clicking the app title in the header returns to the start screen.

### 2. Upload form: `UploadPage`
- Three drop areas: **Source CSV** (required), **Target CSV** (required), **Pipeline run log (JSON, optional)**.
  Use `@mantine/dropzone` at the same major version as `@mantine/core`. Each area also opens a file picker
  on click.
- Check each file in the browser before uploading:
  - The extension is `.csv` or `.json`.
  - The size is at most 10 MB for a CSV, or 1 MB for the run log.
  Show the problem under the file's own drop area. Nothing is sent until every chosen file passes.
- Show each chosen file's name and size, with a button to remove it.
- **Upload** is disabled until both CSV files are chosen. While uploading, show a loading state and
  disable the form.
- Server errors: when `detail.field` names a file, show `detail.message` under that file's drop area. Show
  anything else, including FastAPI's list-style `422`, in an alert above the form.
- A "Download sample files" link serves copies of the demo files from `frontend/public/samples/`:
  `source_customers.csv`, `target_customers.csv` and `pipeline_run.json`. Users can then try the upload
  without their own data.

### 3. Preview: `RunPreviewPage`
- Header: the run ID, the upload time, and a **Start over** button that returns to the upload form.
- For source and target, show the file name, row count and column count, a columns list with each
  column's non-null count and sample values, and a table of the preview rows. Show `null` in the same
  style as the existing `DataCompare` table.
- A small hint listing the columns that appear in both files. Phase 2 uses these for key mapping.
- If a run log was uploaded, show its run ID, status, and step and log counts. If not, show "No run log
  uploaded", with a note that the Pipeline steps and Logs views will be hidden.
- A disabled **Next: map columns** button with the note "Coming in the next phase".

### 4. Keeping the run across page reloads
- Save the run ID in `sessionStorage`. Wrap every read and write in `try/catch`, because it can throw.
- On load, if a saved ID exists, call `GET /api/runs/{id}`:
  - `200`: show the preview.
  - `404` with `run_not_found`: clear the saved ID and show the upload form with the backend's message.

### 5. API client: `src/services/api.js`
- `uploadRun({ source, target, pipelineRun })`: `POST /api/runs` with `FormData`. Don't set
  `content-type`; the browser adds the multipart boundary.
- `getRun(runId)`.
- Errors must keep `status`, `code`, `field` and `message`, so the UI can place them. Extend
  `errorDetail` to handle the structured `detail` form without breaking the string and list forms.
- Add JSDoc types for `RunSummary`, `DatasetInfo` and `ColumnInfo` to `src/types/index.js`.

### 6. Docs
- `frontend/README.md`: describe the new user flow and the new endpoints.

## Testing

- Before the backend is merged: test against a small local stub that returns the contract's examples and
  errors. Don't commit it.
- After the backend is merged into `main`, bring `main` into this branch and test in a browser against the
  real backend:
  - Upload the sample files, with and without the run log.
  - Upload a file over 10 MB. The browser should block it before sending.
  - Upload a broken CSV. The backend's message should appear under the right drop area.
  - Reload on the preview. It should come back. Restart the backend, then reload: you should land on the
    upload form with the "run not found" message.
  - The demo flow is unchanged.
- Check the layout at phone width (375 px) and in dark mode.

## Done checklist

- [ ] `npm run build` succeeds
- [ ] Every browser test above passes against the real backend
- [ ] Sample-data mode still works, with upload disabled
- [ ] The completion report below is filled in; the pull request merges after the backend one

## Out of scope for Phase 1

Column mapping, checks on uploaded data, and the AI on uploaded data.

---

## Questions for the other session

## Completion report
- Branch / PR:
- Deviations from the contract:
- Anything not done, and why:
