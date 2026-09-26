# API contract

The single source of truth for the HTTP API between the frontend and the backend. Only the FE session edits
this file, and only between phases (see [README.md](README.md)). The Pydantic models in `src/api/schemas.py`
must match it.

- Base URL in local development: `http://localhost:8000`
- JSON bodies use `snake_case` keys. Missing values are JSON `null`, never `NaN`.
- CORS allows the origins in the `CORS_ORIGINS` env var (the Vite dev server by default) with methods
  `GET`, `POST` and `OPTIONS`.

| Method | Path | Since | Purpose |
|---|---|---|---|
| `GET` | `/health` | existing | Is the backend up, and is an LLM configured? |
| `GET` | `/api/demo/scenario` | existing | Demo run: execution summary and validation results |
| `GET` | `/api/demo/run` | existing | Demo run: pipeline run record and raw rows |
| `POST` | `/api/investigate` | existing | AI investigation |
| `POST` | `/api/runs` | **Phase 1** | Upload the source CSV, the target CSV and an optional run log |
| `GET` | `/api/runs/{run_id}` | **Phase 1** | Fetch an uploaded run's summary again |

---

## Existing endpoints (unchanged in Phase 1)

These are implemented and tested. Don't change them.

### `GET /health`
```json
{ "status": "ok", "llm_configured": true, "details": { "provider": "AnthropicProvider", "model": "claude-sonnet-5" } }
```
Without an API key: `"llm_configured": false, "details": { "error": "No API key set for provider 'anthropic'. Set LLM_API_KEY." }`.

### `GET /api/demo/scenario`
Model: `DemoScenarioResponse`.
```json
{
  "pipeline_name": "Customer Nightly Sync",
  "pipeline_description": "Nightly customer sync pipeline. ...",
  "status": "FAILED",
  "execution_summary": {
    "source_records": 20, "target_records": 23, "run_id": "run-2024-04-05-0200",
    "reported_run_status": "SUCCESS", "started_at": "2024-04-05T02:00:00Z", "finished_at": "2024-04-05T02:03:41Z"
  },
  "validation_summary": { "total_checks": 6, "passed_checks": 0, "failed_checks": 6 },
  "validation_results": [
    {
      "name": "duplicate_customer_id", "status": "FAILED", "severity": "HIGH",
      "summary": "5 customer ID(s) duplicated in target (5 extra row(s))",
      "metrics": { "affected_records": 10, "duplicate_ids": 5, "extra_rows": 5 },
      "evidence": ["customer_id 1012 appears 2 times in target", "..."]
    }
  ]
}
```
`status` is `PASSED` or `FAILED`. `severity` is `HIGH`, `MEDIUM` or `LOW`. `metrics` values are numbers
or `{value: count}` maps. `evidence` has at most 5 lines plus an optional `"... and N more"` line.

### `GET /api/demo/run`
Model: `DemoRunResponse`.
```json
{
  "pipeline_run": {
    "run_id": "run-2024-04-05-0200", "pipeline": "customer_nightly_sync", "status": "SUCCESS",
    "started_at": "2024-04-05T02:00:00Z", "finished_at": "2024-04-05T02:03:41Z",
    "config": { "batch_size": 5 },
    "steps": [ { "name": "extract", "status": "SUCCESS", "rows_in": 20, "rows_out": 20 } ],
    "logs": [ "02:00:00 INFO  extract: read 20 rows from source_customers.csv" ]
  },
  "source": [ { "customer_id": "1001", "name": "Alice Carter", "email": "Alice.Carter@example.com", "country": "US", "signup_date": "2024-01-05", "status": "active" } ],
  "target": [ { "customer_id": null, "name": "Tara Novak", "...": "..." } ]
}
```

### `POST /api/investigate`
Model: `InvestigateRequest`, then `InvestigateResponse`. The UI sends:
```json
{ "pipeline_name": "Customer Nightly Sync", "pipeline_description": "...", "execution_summary": { "...": "..." }, "use_demo_data": true }
```
The response has `summary`, `observed_facts`, `hypotheses` (`hypothesis`, `status`
`SUPPORTED|REJECTED|INCONCLUSIVE`, `evidence`, `reasoning`), `root_cause_status` (`IDENTIFIED|INCONCLUSIVE`),
`root_cause`, `root_cause_evidence`, `root_cause_reasoning`, `evidence` (alias of `observed_facts`),
`recommended_fix`, `regression_test` (string), `investigation_trace` (`stage`, `description`) and
`evidence_warnings`. Evidence lines look like `"[validation.duplicate_customer_id] text"`.

Errors use `{"detail": "<message>"}`: `503` (no LLM configured), `504` (LLM timeout), `502` (provider error
or invalid LLM output), `500` (unexpected). Request validation errors are FastAPI's default `422`.

---

## Phase 1: uploads

### Limits

| Limit | Value | Error when exceeded |
|---|---|---|
| CSV file size | 10 MB (10,485,760 bytes) each | `413`, code `file_too_large` |
| CSV data rows (excluding the header) | 50,000 each | `422`, code `too_many_rows` |
| Run log file size | 1 MB (1,048,576 bytes) | `413`, code `file_too_large` |
| Runs kept in memory | 20; creating a 21st evicts the oldest | none |

### `POST /api/runs`

`multipart/form-data` with these fields:

| Field | Required | Content |
|---|---|---|
| `source_file` | yes | CSV: UTF-8 (a BOM is allowed), comma-separated, first row is the header |
| `target_file` | yes | CSV, same rules |
| `pipeline_run_file` | no | JSON object describing the pipeline run (rules below) |

**CSV rules.** Parse every value as a string (`dtype=str`). An empty cell becomes `null`. The strings `NA`,
`null` and `None` are kept as text, not treated as missing. Leading and trailing spaces in header names are
trimmed. The file is rejected if it:
- is empty, or contains a header but no data rows: `invalid_csv`
- isn't valid UTF-8: `invalid_encoding`
- has an empty or duplicate header name after trimming: `invalid_header`
- can't be parsed, for example because a row has more fields than the header: `invalid_csv`

**Run log rules.** It must be a JSON object: `invalid_pipeline_run`. Every field is optional. If present:
`steps` must be a list of objects that each have a string `name`, and `logs` must be a list of strings.
Any other field is kept as-is. `null` or a missing field means "not provided".

**`201 Created`** returns a `RunSummary`:
```json
{
  "run_id": "run_3f9a1c2b7d4e",
  "created_at": "2026-09-26T10:15:00Z",
  "source": {
    "file_name": "source_customers.csv",
    "row_count": 20,
    "columns": [
      { "name": "customer_id", "non_null_count": 20, "sample_values": ["1001", "1002", "1003"] },
      { "name": "email", "non_null_count": 20, "sample_values": ["Alice.Carter@example.com", "bob.singh@example.com", "chloe.martin@example.com"] }
    ],
    "preview": [
      { "customer_id": "1001", "email": "Alice.Carter@example.com" }
    ]
  },
  "target": {
    "file_name": "target_customers.csv",
    "row_count": 23,
    "columns": [ { "name": "customer_id", "non_null_count": 22, "sample_values": ["1001", "1002", "1003"] } ],
    "preview": [ { "customer_id": null, "email": "tara.novak@example.com" } ]
  },
  "pipeline_run": null
}
```
- `run_id`: `run_` followed by 12 lowercase hex characters.
- `created_at`: UTC, ISO 8601, second precision, with a `Z` suffix.
- `columns`: in file order. `sample_values` holds up to 3 distinct non-null values in order of first appearance.
- `preview`: the first 20 rows in file order, with every column present in each row and `null` for empty cells.
- `pipeline_run`: the parsed run log object, or `null` if none was uploaded.

**Errors.** Upload errors use a structured `detail`:
```json
{ "detail": { "code": "too_many_rows", "message": "target_file has 61,204 data rows; the limit is 50,000.", "field": "target_file" } }
```

| Status | `code` | When |
|---|---|---|
| `413` | `file_too_large` | A file is over its size limit |
| `422` | `invalid_encoding` | A CSV isn't UTF-8 |
| `422` | `invalid_csv` | A CSV is empty, has no data rows, or can't be parsed |
| `422` | `invalid_header` | A header name is empty or duplicated |
| `422` | `too_many_rows` | A CSV has more than 50,000 data rows |
| `422` | `invalid_pipeline_run` | The run log isn't valid JSON or breaks the rules above |

`field` is `source_file`, `target_file` or `pipeline_run_file`. `message` is a plain sentence that the UI
shows as-is. When several files are bad, report the first in this order: `source_file`, `target_file`,
`pipeline_run_file`. A missing required field gets FastAPI's default `422`, where `detail` is a list. The
frontend handles both forms.

### `GET /api/runs/{run_id}`

`200` returns the same `RunSummary` as the upload response.

`404` if the ID is unknown, including after a backend restart or eviction:
```json
{ "detail": { "code": "run_not_found", "message": "Run run_3f9a1c2b7d4e was not found. It may have expired; upload the files again.", "field": null } }
```

### Planned for later phases (not part of Phase 1)

These will be specified in full when their phase starts. They are listed here so Phase 1 code doesn't
block them.
- Phase 2: `POST /api/runs/{run_id}/mapping` (key column, and optional email and status columns),
  `GET /api/runs/{run_id}/scenario` (same format as `/api/demo/scenario`), and `GET /api/runs/{run_id}/data`
  (same format as `/api/demo/run`). Keep the full parsed DataFrames in the run store, not just the preview.
- Phase 3: `POST /api/runs/{run_id}/investigate`.
