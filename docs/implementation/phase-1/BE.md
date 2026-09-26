# Phase 1: Backend instructions (uploads)

For the **BE session**. Read [`../README.md`](../README.md) (process and ownership) and the "Phase 1:
uploads" section of [`../CONTRACT.md`](../CONTRACT.md) first. The contract is the spec. This file says
how to build it and what to check.

## Goal

A user can upload a source CSV, a target CSV and an optional pipeline run JSON file. The backend
validates them, keeps them in memory under a new run ID, and returns a summary with a preview. The
summary can be fetched again by ID.

## Before you start

1. Pull the latest `main` and create your working branch from it.
2. Confirm the baseline: `pip install -r requirements.txt && python -m pytest -q`. All tests should pass.
3. Only touch files you own: `src/`, `tests/`, `requirements.txt`, and the backend and run sections of the root
   `README.md`. Don't touch `frontend/` or `docs/implementation/`, except for the completion report at
   the bottom of this file.

## Tasks

### 1. Dependency
- Add `python-multipart>=0.0.9` to `requirements.txt`. FastAPI needs it for `UploadFile` and `Form`.

### 2. Parsing and validation: new module `src/runs/ingest.py`
- Add `src/runs/__init__.py` (empty).
- Define the limits as module constants, so tests can monkeypatch them:
  `MAX_CSV_BYTES = 10 * 1024 * 1024`, `MAX_CSV_ROWS = 50_000`, `MAX_RUN_LOG_BYTES = 1024 * 1024`.
- Define `UploadError(Exception)` with `status_code`, `code`, `message` and `field`.
- `read_limited(upload, limit, field)`: read the upload in chunks and raise `413 file_too_large` as soon
  as it goes past `limit`. Don't read the whole file into memory first.
- `parse_csv(data: bytes, field: str) -> pd.DataFrame`:
  - Decode as UTF-8 with `utf-8-sig`, so a BOM is stripped. On `UnicodeDecodeError`, raise `invalid_encoding`.
  - Parse with `pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=[""])`.
    This matches how `src/data/scenario.py::load_scenario` reads the demo files, so later phases can reuse
    the validation code unchanged.
  - Map these to the contract's error codes: `pandas.errors.EmptyDataError`, `ParserError`, zero data
    rows, header problems, and more than `MAX_CSV_ROWS` rows.
  - Duplicate headers: pandas renames them to `name.1`, so it hides duplicates. Check for duplicates in
    the raw header line instead, parsed with the `csv` module, after trimming each name. Also reject empty
    names, which pandas turns into `Unnamed: N`.
  - Trim spaces from the column names.
- `parse_pipeline_run(data: bytes | None) -> dict | None`: apply the run log rules in the contract.
- Error messages are shown to users exactly as written. Make them specific and name the file field, for
  example `"source_file has 2 columns named 'email'. Column names must be unique."`

### 3. Run store: new module `src/runs/store.py`
- `RunRecord` dataclass: `run_id`, `created_at` (a UTC `datetime`), `source_name`, `target_name`,
  `source: pd.DataFrame`, `target: pd.DataFrame`, `pipeline_run: dict | None`.
- `RunStore`: a thread-safe store (use `threading.Lock`) that keeps insertion order, with `MAX_RUNS = 20`.
  - `add(record)` evicts the oldest record when full.
  - `get(run_id)` returns the record or `None`.
  - `clear()` is for tests.
- One module-level instance, `store = RunStore()`, used through a FastAPI dependency (`get_run_store`)
  so tests can override it.
- Keep the **full** DataFrames. Phase 2 runs the validations on them.
- Run IDs: `"run_" + secrets.token_hex(6)`.

### 4. Summary: `src/runs/summary.py` (or inside `store.py`)
- `summarize(record) -> dict` builds the contract's `RunSummary`.
- Build each dataset's `columns` and `preview`, with `PREVIEW_ROWS = 20` and `SAMPLE_VALUES = 3`.
- Convert missing values to `None` the same way `src/validation/suite.py::_records` does. Reuse that
  function; don't copy it.

### 5. API: `src/api/main.py` and `src/api/schemas.py`
- Pydantic models: `ColumnInfo`, `DatasetInfo`, `RunSummary`, and `UploadErrorDetail` (`code`,
  `message`, `field`).
- `POST /api/runs`: takes `source_file: UploadFile`, `target_file: UploadFile` and
  `pipeline_run_file: UploadFile | None = None`. Returns status `201` and a `RunSummary` model.
  - Validate in contract order: source, then target, then run log. Stop at the first error.
  - Raise `HTTPException(status_code, detail={"code", "message", "field"})` from `UploadError`.
  - A browser sends an empty file part when no file is chosen. Treat a `pipeline_run_file` with an empty
    filename or zero bytes as not provided.
- `GET /api/runs/{run_id}`: returns `200` with a `RunSummary`, or `404` with code `run_not_found`, the
  message from the contract, and `"field": null`.
- Don't change the existing endpoints.

### 6. Tests: new `tests/test_runs.py`
Use `TestClient` and the files in `data/` as real upload fixtures. Build bad files in the test.
Cover at least:
- Uploading the demo source and target files returns `201`:
  - `row_count` is 20 and 23.
  - The columns are in file order.
  - `preview` has exactly the first 20 rows.
  - The target `customer_id` column has `non_null_count` 22. Its one empty cell is on row 23, outside the
    preview.
  - A small CSV built in the test with an empty cell shows `null` for that cell in `preview`.
  - `sample_values` has at most 3 distinct values.
  - `pipeline_run` is `null`.
- Uploading with `data/pipeline_run.json` returns that object as `pipeline_run`.
- `GET /api/runs/{id}` returns the same body as the upload.
- An unknown ID returns `404` with code `run_not_found`.
- Each error code, including which `field` it names:
  - `file_too_large` (monkeypatch `MAX_CSV_BYTES` to a small number)
  - `too_many_rows` (monkeypatch `MAX_CSV_ROWS`)
  - `invalid_encoding` (for example `"café".encode("latin-1")`)
  - `invalid_csv`, for both an empty file and a header with no rows
  - `invalid_header`, for both a duplicate and an empty name
  - `invalid_pipeline_run`, for both invalid JSON and a list instead of an object
- When both files are bad, the error names `source_file`.
- A missing `target_file` returns `422`.
- Creating 21 runs makes the first ID return `404`.
- `NA` in a CSV cell stays the string `"NA"`. A BOM-prefixed file parses with a clean first column name.
- The demo endpoints still behave the same. The existing tests cover this; just keep them passing.

### 7. Docs
- Root `README.md`: add `src/runs/` to the backend components table, and mention the upload endpoints and
  limits in one or two lines.

## Done checklist

- [ ] `python -m pytest -q` passes, with the new tests included
- [ ] Manual check with the backend running:
      `curl -s -F source_file=@data/source_customers.csv -F target_file=@data/target_customers.csv localhost:8000/api/runs`
      returns `201` and a summary matching the contract. `curl` on the returned `/api/runs/{id}` returns the same body.
- [ ] A too-large or broken file returns the contract's `{"detail": {"code", "message", "field"}}` form
- [ ] The demo endpoints and `/api/investigate` are unchanged
- [ ] No files outside your ownership were changed
- [ ] The completion report below is filled in, and the work is pushed with a pull request into `main`

## Out of scope for Phase 1

Column mapping, running validations on uploads, and investigating uploads are Phase 2 and 3 work. Don't
build them yet, even partially. Only keep the full DataFrames in the store, as described above.

---

## Questions for the other session

_(BE session: add anything in the contract that is unclear or impossible here, then continue with the rest.)_

## Completion report

_(BE session: fill in when done.)_
- Branch / PR:
- Test count before → after:
- Deviations from the contract (should be none):
- Anything not done, and why:
