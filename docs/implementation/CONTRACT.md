# AI Software Reliability Engineer
## Frontend ↔ Backend API Contract

**Version:** 2.2 (2.1 added multiple databases; 2.2 adds investigation fixes and the suggested CSV; both additive,
backward compatible)  
**Status:** APPROVED FOR IMPLEMENTATION  
**Owner:** Shared FE + BE contract  
**Last Updated:** 2026-09-26

---

# 1. Purpose

This document is the single source of truth for the frontend/backend integration of the BITSoM Vertex challenge application.

The application demonstrates an AI Software Reliability Engineer that can:

1. Allow the user to select an existing target table.
2. Accept one CSV data file from the user.
3. Inspect the target table schema and constraints.
4. Validate the uploaded data against the target contract.
5. Fail the run with real, deterministic evidence when validation fails.
6. Load the data into the target table when validation succeeds.
7. Use AI to investigate failed runs.
8. Identify likely root cause using actual evidence.
9. Recommend corrective action.
10. Allow the user to correct the CSV and retry.
11. Demonstrate a successful recovery.

The core workflow is:

    TARGET TABLE
          ↓
    SELECT TARGET
          ↓
    UPLOAD ONE CSV
          ↓
    CREATE RUN
          ↓
    DISCOVER TARGET CONTRACT
          ↓
    VALIDATE
          ↓
       ┌──┴──┐
       ↓     ↓
     PASS   FAIL
       ↓     ↓
      LOAD  EVIDENCE
       ↓     ↓
    SUCCESS  AI INVESTIGATION
                 ↓
             ROOT CAUSE
                 ↓
          RECOMMENDED FIX
                 ↓
          USER CORRECTS CSV
                 ↓
               RETRY
                 ↓
             VALIDATION
                 ↓
               SUCCESS

# 2. Contract Ownership

This document is shared by both Claude Code sessions.

## Backend owns

- SQLite target database
- Target table definitions
- Target schema/DDL discovery
- CSV parsing
- Validation
- Pipeline execution
- Data loading
- Run state
- Failure evidence
- AI investigation
- Retry execution
- API implementation

## Frontend owns

- Target selection UI
- CSV upload UI
- Run initiation
- Run progress UI
- Validation result UI
- Failure UI
- AI investigation UI
- Root cause presentation
- Recommended fix presentation
- Corrected-file upload
- Retry UI
- Success UI

## Shared ownership

The API contract is shared.

Neither frontend nor backend may independently change an API request, response, field name, status value, or error format without first updating this document.

If implementation reveals a required contract change:

1. STOP implementation of the affected feature.
2. Document the proposed contract change.
3. Update this document.
4. Ensure both FE and BE sessions use the updated version.
5. Then continue implementation.

Do NOT silently change the contract.

# 3. Scope

## In scope

- SQLite target database
- Existing target tables
- CSV input
- Target schema/DDL discovery
- Deterministic validation
- Transactional loading
- Failure evidence
- AI investigation
- Root-cause analysis
- Recommended remediation
- Corrected CSV retry
- Successful recovery
- Demo scenario
- Run history during the application session

## Out of scope for the challenge prototype

Do NOT add these unless explicitly requested later:

- Authentication
- RBAC
- Multi-tenant architecture
- Kubernetes
- Cloud deployment
- Distributed execution
- Kafka
- Spark
- Databricks
- Airflow
- LangChain
- CrewAI
- Vector database
- RAG infrastructure
- Multi-agent architecture
- Arbitrary AI-generated code execution
- Production-grade persistent run database
- Multiple simultaneous users
- Large-scale distributed file processing

The prototype should remain simple, reliable and demonstrable.

# 4. Data Flow

The application uses an existing SQLite database containing target tables.

The user does NOT upload a target CSV.

The user uploads only the incoming data file.

Example:

    SQLite
      |
      +-- customer
            |
            +-- customer_id INTEGER PRIMARY KEY
            +-- name TEXT NOT NULL
            +-- email TEXT UNIQUE NOT NULL
            +-- country TEXT
            +-- signup_date TEXT
            +-- status TEXT CHECK(...)

User uploads:

    customer.csv

The application discovers the target contract and validates the CSV before attempting to load it.

# 5. Target Tables

For the prototype, target tables are backed by SQLite.

The backend may maintain a seeded demo database.

Example target:

    customer

Example schema:

    CREATE TABLE customer (
        customer_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        country TEXT,
        signup_date TEXT,
        status TEXT CHECK(status IN ('ACTIVE', 'INACTIVE', 'CHURNED'))
    );

The exact implementation may use a seeded database file.

The frontend must NOT hardcode the target schema.

The frontend obtains target information through the API.

# 5a. Databases (v2.1)

The backend offers every SQLite file (`*.db`, `*.sqlite`, `*.sqlite3`) in its database folder (`TARGET_DB_DIR`,
default `data/databases/`) as a database, plus the default database (`TARGET_DB_PATH`, default
`data/databases/crm.db`). Every table in a database is a possible target; `target_id` is the table name.

The user selects a database, then a table from that database. Requests that omit `database_id` use the default
database, so v2.0 clients keep working.

## GET /api/databases

Status: `200 OK`

```json
{
  "databases": [
    { "database_id": "crm", "display_name": "CRM", "file_name": "crm.db", "database_type": "sqlite",
      "table_count": 1, "is_default": true },
    { "database_id": "sales", "display_name": "Sales", "file_name": "sales.db", "database_type": "sqlite",
      "table_count": 2, "is_default": false }
  ]
}
```

- The default database is first; the others follow by file name.
- `database_id` is the file name without its extension (a second file with the same name gets its extension
  appended, e.g. `crm_sqlite`). The frontend must use `database_id` and never build file paths.
- Files that are not SQLite databases are not listed.

## database_id on existing endpoints

| Endpoint | Change |
|---|---|
| `GET /api/targets` | Optional query `database_id`. Returns that database's tables. Each target also has `database_id`. |
| `GET /api/targets/{target_id}` | Optional query `database_id`. The response also has `database_id`. |
| `POST /api/runs` | Optional form field `database_id`. |
| `RunSummary` (all run responses) | New field `database_id`: the database the run's target belongs to. |
| `POST /api/runs/{run_id}/retry` | Unchanged request; the new run uses the parent run's database. |

Errors:

| Status | `code` | When |
|---|---|---|
| `404` | `database_not_found` | `database_id` does not name a listed database (`field`: `database_id`) |
| `404` | `target_not_found` | the table does not exist in the chosen database (`field`: `target_id`) |

`description` on a target is optional and omitted when the backend has none for that table.

# 6. Target Selection API

## GET /api/targets

Returns the available target tables.

### Request

No request body.

### Response

Status: `200 OK`

```json
{
  "targets": [
    {
      "target_id": "customer",
      "table_name": "customer",
      "display_name": "Customer",
      "description": "Customer master data",
      "database_type": "sqlite"
    }
  ]
}
```

### Target object

| Field | Type | Required | Description |
|---|---|---:|---|
| target_id | string | yes | Stable identifier used in API calls |
| table_name | string | yes | Actual database table |
| display_name | string | yes | UI-friendly name |
| description | string | no | Target description |
| database_type | string | yes | `sqlite` |

The frontend must use `target_id`.

It must not construct table names itself.

# 7. Target Schema API

## GET /api/targets/{target_id}

Returns the target table's schema and constraints.

### Request

No request body.

### Response

Status: `200 OK`

```json
{
  "target_id": "customer",
  "table_name": "customer",
  "database_type": "sqlite",
  "columns": [
    {
      "name": "customer_id",
      "data_type": "INTEGER",
      "nullable": false,
      "primary_key": true,
      "unique": false
    },
    {
      "name": "name",
      "data_type": "TEXT",
      "nullable": false,
      "primary_key": false,
      "unique": false
    },
    {
      "name": "email",
      "data_type": "TEXT",
      "nullable": false,
      "primary_key": false,
      "unique": true
    },
    {
      "name": "country",
      "data_type": "TEXT",
      "nullable": true,
      "primary_key": false,
      "unique": false
    },
    {
      "name": "signup_date",
      "data_type": "TEXT",
      "nullable": true,
      "primary_key": false,
      "unique": false
    },
    {
      "name": "status",
      "data_type": "TEXT",
      "nullable": true,
      "primary_key": false,
      "unique": false
    }
  ],
  "constraints": [
    {
      "type": "PRIMARY_KEY",
      "columns": ["customer_id"],
      "description": "customer_id must be unique and non-null"
    },
    {
      "type": "UNIQUE",
      "columns": ["email"],
      "description": "email must be unique"
    },
    {
      "type": "NOT_NULL",
      "columns": ["name", "email"],
      "description": "Required fields cannot be null"
    },
    {
      "type": "CHECK",
      "columns": ["status"],
      "allowed_values": [
        "ACTIVE",
        "INACTIVE",
        "CHURNED"
      ],
      "description": "status must contain an allowed value"
    }
  ]
}
```

The backend is responsible for discovering this information from SQLite.

The frontend must not duplicate or hardcode these constraints.

# 8. Validation Rules

Validation is deterministic.

AI does NOT determine whether a database constraint passed or failed.

The validation engine is responsible for producing factual evidence.

At minimum, the backend should support these validations for the prototype:

## 8.1 Required columns

Every required target column must exist in the uploaded CSV.

## 8.2 Unexpected columns

Unexpected columns should be reported.

Preferred demo behavior:

    WARNING

rather than automatic failure, unless the target loader cannot safely handle the column.

## 8.3 Data type compatibility

Uploaded values must be compatible with the target column type.

Example:

    customer_id INTEGER

Uploaded:

    customer_id = "ABC"

Result:

    FAILED

## 8.4 NOT NULL

If the target column is NOT NULL:

    null value → FAILED

## 8.5 PRIMARY KEY uniqueness

Primary key values must:

- not be null
- be unique within the uploaded dataset
- not conflict with existing target records when using APPEND mode

## 8.6 UNIQUE constraints

Unique columns must:

- not contain duplicates within the uploaded data
- not conflict with existing target records

## 8.7 CHECK constraints

Values must satisfy the target table's CHECK constraint.

Example:

    status IN ('ACTIVE', 'INACTIVE', 'CHURNED')

Invalid:

    status = 'PENDING'

Result:

    FAILED

## 8.8 Foreign keys

If a target table contains a foreign key and the prototype database provides the referenced table, the validation may check referential integrity.

This is optional for the first implementation.

Do not block the core demo waiting for foreign-key support.

# 9. Validation Result Contract

Every validation produces a common result structure.

```json
{
  "name": "primary_key_uniqueness",
  "status": "FAILED",
  "severity": "ERROR",
  "summary": "Duplicate customer_id values were found in the uploaded data.",
  "metrics": {
    "affected_rows": 2,
    "duplicate_values": 1
  },
  "evidence": [
    "[validation.primary_key_uniqueness.001] customer_id=101 appears 2 times"
  ]
}
```

## Allowed status values

    PASSED
    FAILED
    WARNING
    SKIPPED

## Allowed severity values

    INFO
    WARNING
    ERROR

Evidence must be deterministic.

The backend must never fabricate validation evidence.

# 10. Evidence Rules

Every failed validation must produce evidence that can be traced back to the actual uploaded data or target definition.

Evidence should be capped to prevent huge responses.

Default:

    Maximum 5 evidence items per validation.

Do not send entire datasets to the LLM.

Dataset summaries may be sent.

Raw data should not be sent unnecessarily.

# 11. Run Creation

## POST /api/runs

Creates and executes a pipeline run using one uploaded CSV.

### Content-Type

    multipart/form-data

### Form fields

| Field | Type | Required | Description |
|---|---|---:|---|
| target_id | string | yes | Target table identifier |
| file | file | yes | Incoming CSV |
| parent_run_id | string | no | Previous failed run being retried |

### File requirements

For the prototype:

- CSV only
- UTF-8
- maximum 10 MB
- must contain a header row
- must contain at least one data row
- malformed CSV must produce a structured error

# 12. Run Processing

When `POST /api/runs` is called:

1. Create a unique run ID.
2. Resolve the target.
3. Inspect the target schema and constraints.
4. Parse the uploaded CSV.
5. Run deterministic validations.
6. If validation fails, do NOT modify the target table. Run becomes `FAILED_VALIDATION`.
7. If all required validations pass, begin database transaction.
8. Load the data into the target table.
9. If load succeeds, COMMIT and mark `SUCCEEDED`.
10. If the database load fails unexpectedly, ROLLBACK and mark `LOAD_FAILED`.

# 13. Run Status

Allowed run statuses:

    CREATED
    VALIDATING
    FAILED_VALIDATION
    LOADING
    SUCCEEDED
    LOAD_FAILED

AI investigation is a separate operation and does not change the underlying pipeline run status.

# 14. Run Response

## POST /api/runs

### Success response

Status:

    201 Created

Example:

```json
{
  "run_id": "run_a81f4c2d91ab",
  "parent_run_id": null,
  "target_id": "customer",
  "target_table": "customer",
  "file_name": "customer.csv",
  "status": "FAILED_VALIDATION",
  "created_at": "2026-09-26T10:30:00Z",
  "completed_at": "2026-09-26T10:30:01Z",
  "summary": {
    "rows_received": 1000,
    "checks_total": 6,
    "checks_passed": 4,
    "checks_failed": 2
  },
  "validation_results": [
    {
      "name": "primary_key_uniqueness",
      "status": "FAILED",
      "severity": "ERROR",
      "summary": "Duplicate customer_id values were found.",
      "metrics": {
        "affected_rows": 2,
        "duplicate_values": 1
      },
      "evidence": [
        "[validation.primary_key_uniqueness.001] customer_id=101 appears 2 times"
      ]
    }
  ],
  "load_result": null
}
```

For a successful run:

```json
{
  "run_id": "run_xyz123",
  "parent_run_id": "run_previous123",
  "target_id": "customer",
  "target_table": "customer",
  "file_name": "customer_fixed.csv",
  "status": "SUCCEEDED",
  "created_at": "2026-09-26T10:35:00Z",
  "completed_at": "2026-09-26T10:35:01Z",
  "summary": {
    "rows_received": 1000,
    "checks_total": 6,
    "checks_passed": 6,
    "checks_failed": 0
  },
  "validation_results": [],
  "load_result": {
    "rows_loaded": 1000,
    "target_table": "customer"
  }
}
```

# 15. GET Run

## GET /api/runs/{run_id}

Returns the current stored run information.

### Response

Status:

    200 OK

Response uses the same `RunSummary` structure.

### Unknown run

Status:

    404 Not Found

```json
{
  "detail": {
    "code": "run_not_found",
    "message": "Run 'run_unknown' was not found.",
    "field": "run_id"
  }
}
```

# 16. AI Investigation

AI investigation is only available for a failed run.

## POST /api/runs/{run_id}/investigate

The backend builds the AI evidence package from the actual run.

The frontend does NOT send validation results to the AI endpoint.

### Request

No request body is required.

### Valid run

The run must have:

    status = FAILED_VALIDATION

or:

    status = LOAD_FAILED

### Response

Status:

    200 OK

The response should preserve the existing investigation structure where compatible:

```json
{
  "run_id": "run_a81f4c2d91ab",
  "summary": "The uploaded data failed two target-table constraints.",
  "observed_facts": [
    "customer_id=101 appears more than once.",
    "status='PENDING' violates the target status constraint."
  ],
  "hypotheses": [
    {
      "hypothesis": "Duplicate primary-key values caused the validation failure.",
      "status": "SUPPORTED",
      "evidence": [
        "[validation.primary_key_uniqueness.001]"
      ],
      "reasoning": "The target defines customer_id as a primary key and the uploaded data contains a duplicate value."
    },
    {
      "hypothesis": "A database connectivity problem caused the failure.",
      "status": "REJECTED",
      "evidence": [],
      "reasoning": "The validation engine successfully inspected the target and processed the uploaded dataset."
    }
  ],
  "root_cause_status": "IDENTIFIED",
  "root_cause": "The uploaded data violates the target table's primary-key and CHECK constraints.",
  "root_cause_evidence": [
    "[validation.primary_key_uniqueness.001]",
    "[validation.check.001]"
  ],
  "root_cause_reasoning": "The target contract requires unique customer_id values and restricts status values. The uploaded data violates both constraints.",
  "recommended_fix": "Correct the duplicate customer_id values and replace invalid status values with an allowed status before retrying.",
  "regression_test": "Verify primary-key uniqueness and allowed status values before loading the target table.",
  "investigation_trace": [
    {
      "stage": "evidence_review",
      "description": "Reviewed deterministic validation results."
    },
    {
      "stage": "hypothesis_generation",
      "description": "Generated possible causes from the observed evidence."
    },
    {
      "stage": "root_cause_analysis",
      "description": "Selected the root cause supported by the available evidence."
    }
  ],
  "evidence_warnings": []
}
```

## Investigation additions (v2.2)

The response also has these fields. They are always present (empty lists when the AI gave none), so a client that
ignores them keeps working:

| Field | Type | Meaning |
|---|---|---|
| `cause_groups` | `CauseGroup[]` | The failures grouped by likely origin, not by check |
| `row_fixes` | `RowFix[]` | Suggested changes to the uploaded file, checked by the backend against the file |
| `prevention` | `string[]` | Steps for whoever produces the file, so the problem doesn't recur |
| `model` | `string \| null` | The model that produced the investigation |

```json
{
  "cause_groups": [
    {"title": "Exporting system formats values differently", "category": "SOURCE_FORMAT",
     "explanation": "An ID carries a CUST- prefix and one status is lower-case.",
     "checks": ["data_type_compatibility", "check_constraints"], "rows": [7, 8],
     "evidence": ["[dataset.column_profiles] customer_id is an integer in 6 of 7 rows"]}
  ],
  "row_fixes": [
    {"row": 7, "column": "customer_id", "action": "REPLACE", "current_value": "CUST-1016", "suggested_value": "1016",
     "reason": "Strip the prefix; the other IDs are plain integers.", "confidence": "HIGH",
     "evidence": "[validation.data_type_compatibility.001]", "satisfies_constraints": true},
    {"row": 3, "column": "name", "action": "NEEDS_DECISION", "current_value": "", "suggested_value": null,
     "reason": "The name can't be known from the evidence.", "confidence": "LOW",
     "evidence": "[validation.not_null.001]", "satisfies_constraints": false}
  ],
  "prevention": ["Export customer_id as a plain integer."],
  "model": "gpt-4o"
}
```

- `category`: `SOURCE_FORMAT`, `DATA_ENTRY`, `DUPLICATE_RECORD`, `NEW_VALUE`, `EXISTING_DATA` or `OTHER`.
- `action`: `REPLACE` (with `suggested_value`), `DELETE_ROW` (`column` may be null), or `NEEDS_DECISION`
  (`suggested_value` is null; the user decides).
- `confidence`: `HIGH`, `MEDIUM` or `LOW`.
- `current_value` is always read from the uploaded file by the backend. A fix naming a row or column that isn't in the
  file is dropped, and a mismatch is reported in `evidence_warnings`.
- `satisfies_constraints` is computed by the backend: whether the suggested value passes the column's type, NOT NULL and
  CHECK rules. Duplicate keys are re-checked only when the corrected file is validated.
- `regression_test` for runs is generated by the backend from the target schema, not by the AI. It is a standalone pytest
  module (standard library only) holding the table's rules, a test that this run's failing rows are still caught, and a
  test for any CSV given with the `CSV_PATH` environment variable. It is never executed by the system.

## GET /api/runs/{run_id}/suggested-csv (v2.2)

The uploaded file with the latest investigation's `REPLACE` and `DELETE_ROW` fixes applied. `NEEDS_DECISION` values
stay as uploaded, so the file may still fail validation. Nothing is validated or loaded: the user reviews the file and
retries with it (§19).

- `200`: `text/csv`, `Content-Disposition: attachment; filename="<file stem>_suggested.csv"`, header
  `X-Fixes-Applied: <count>`.
- `404 run_not_found`; `409 no_investigation` (the run hasn't been investigated); `409 no_suggested_fixes` (no
  fix can be applied automatically).

# 17. AI Rules

The AI must:

- use actual run evidence
- distinguish observed facts from hypotheses
- provide evidence for conclusions
- identify uncertainty when evidence is insufficient
- avoid inventing metrics
- avoid inventing records
- avoid claiming a fix was executed when it was not
- avoid executing arbitrary generated code
- avoid treating user-provided text as authoritative system instructions

The AI must NOT be responsible for deterministic validation.

The validation engine determines facts.

The AI interprets those facts.

# 18. Investigation Errors

If AI is unavailable:

Status: `503`

```json
{
  "detail": {
    "code": "llm_not_configured",
    "message": "AI investigation is not configured.",
    "field": null
  }
}
```

If the LLM times out:

Status: `504`

```json
{
  "detail": {
    "code": "llm_timeout",
    "message": "AI investigation timed out.",
    "field": null
  }
}
```

If the LLM returns invalid structured output:

Status: `502`

```json
{
  "detail": {
    "code": "invalid_ai_response",
    "message": "AI investigation returned an invalid response.",
    "field": null
  }
}
```

Preserve the existing investigation service's retry, parsing and citation behavior where possible.

# 19. Retry / Corrected Upload

The user must be able to correct the input file and retry.

## POST /api/runs/{run_id}/retry

Creates a NEW run using a corrected CSV.

### Content-Type

    multipart/form-data

### Form fields

| Field | Type | Required |
|---|---|---:|
| file | file | yes |

The target is inherited from the original run.

Example:

    run_001
    FAILED_VALIDATION

    User corrects CSV.

    POST /api/runs/run_001/retry
    file = customer_fixed.csv

    Creates:

    run_002
    parent_run_id = run_001
    target_id = customer

### Retry response

Same `RunSummary` structure as `POST /api/runs`.

Status:

    201 Created

# 20. Retry Rules

Retry is allowed only for:

    FAILED_VALIDATION
    LOAD_FAILED

The original run must remain unchanged.

Each retry receives a new run ID.

# 21. Load Semantics

For the prototype, loading uses:

    APPEND

The uploaded records are inserted into the selected target table.

The backend must validate against:

1. the uploaded dataset
2. relevant existing target data

For example, if `customer_id=101` already exists in the target and `customer_id` is a primary key, the upload must fail before committing the insert.

No partial successful load is allowed.

Use a database transaction:

    BEGIN
       validate/load
    COMMIT

or:

    BEGIN
       failure
    ROLLBACK

# 22. Success Conditions

A run is successful only when:

1. CSV parsing succeeds.
2. Target schema is available.
3. Required columns exist.
4. Data types are compatible.
5. Required constraints pass.
6. Existing-target conflicts pass.
7. Database insert succeeds.
8. Transaction commits successfully.

Then:

    status = SUCCEEDED

and:

```json
{
  "load_result": {
    "rows_loaded": 1000,
    "target_table": "customer"
  }
}
```

# 23. Failure Conditions

Validation failure:

    status = FAILED_VALIDATION

Database failure:

    status = LOAD_FAILED

A validation failure must prevent database modification.

The frontend must clearly distinguish:

    Validation Failure

from:

    Load Failure

# 24. Frontend State Model

The frontend should present these high-level states:

    TARGET_SELECTION
    UPLOAD
    RUNNING
    VALIDATION_FAILED
    AI_INVESTIGATION
    SUCCESS
    LOAD_FAILED
    RETRY_UPLOAD
    ERROR

These are UI states.

The backend run statuses remain:

    CREATED
    VALIDATING
    FAILED_VALIDATION
    LOADING
    SUCCEEDED
    LOAD_FAILED

# 25. Frontend Workflow

1. Load available targets:
   `GET /api/targets`

2. User selects target.

3. Optionally display target schema:
   `GET /api/targets/{target_id}`

4. User uploads ONE CSV.

5. Frontend sends:
   `POST /api/runs`

6. Display validation/progress.

7. If `FAILED_VALIDATION`, show:
   - failed checks
   - severity
   - metrics
   - evidence
   - Investigate with AI

8. User clicks Investigate with AI:
   `POST /api/runs/{run_id}/investigate`

9. Display:
   - observed facts
   - hypotheses
   - root cause
   - evidence
   - reasoning
   - recommended fix
   - regression test

10. User corrects the CSV.

11. Frontend calls:
    `POST /api/runs/{failed_run_id}/retry`

12. If successful:
    Display pipeline completion and rows loaded.

# 26. Frontend Must Not Duplicate Backend Validation

The frontend must NOT implement its own copies of:

- duplicate detection
- null detection
- CHECK constraint validation
- datatype validation
- primary-key validation

The backend is the source of truth.

The frontend only renders backend validation results.

# 27. Frontend Must Not Hardcode Target Columns

The frontend must not assume:

    customer_id
    email
    status

or any other target-specific column.

The frontend receives schema information from:

    GET /api/targets/{target_id}

The live upload flow must use API-provided metadata.

# 28. Existing Demo Endpoints

The existing demo endpoints may remain:

    GET /health
    GET /api/demo/scenario
    GET /api/demo/run
    POST /api/investigate

They represent the existing bundled demo and may continue to work.

The live workflow uses the new run-scoped endpoints.

# 29. Live vs Demo

The application may provide:

    Try Demo

and:

    Run Your Data

The demo uses the existing bundled scenario.

The live flow uses:

    Target table
        +
    User CSV
        +
    Runtime validation
        +
    Runtime load/failure
        +
    Run-scoped AI investigation

# 30. Error Contract

All NEW live endpoints must use:

```json
{
  "detail": {
    "code": "error_code",
    "message": "Human-readable message",
    "field": "field_name"
  }
}
```

`field` may be null.

Common error codes:

    target_not_found
    database_not_found
    run_not_found
    invalid_file
    unsupported_file_type
    file_too_large
    empty_file
    malformed_csv
    missing_header
    missing_required_column
    invalid_data_type
    validation_failed
    run_not_retryable
    llm_not_configured
    llm_timeout
    llm_provider_error
    invalid_ai_response
    internal_error

# 31. HTTP Status Codes

Use:

    200 OK
    201 Created
    400 Bad Request
    404 Not Found
    413 Payload Too Large
    422 Unprocessable Entity
    502 Bad Gateway
    503 Service Unavailable
    504 Gateway Timeout
    500 Internal Server Error

# 32. Run Storage

For the challenge prototype, persistent production storage is not required.

An in-memory run store is acceptable.

Maximum retained runs:

    20

Each run should retain enough information for:

- run status
- target
- filename
- validation results
- evidence
- load result
- parent run
- investigation

Do not build a production persistence architecture.

# 33. Security Principles

The application should:

- keep LLM API keys in environment variables
- never expose API keys to the frontend
- never send the entire dataset to the LLM unnecessarily
- cap evidence
- never execute arbitrary AI-generated code
- use parameterized database operations
- validate uploaded files
- use transaction rollback on failed loads
- avoid exposing stack traces through API responses

Authentication/RBAC is out of scope for the prototype.

# 34. AI Evidence Boundary

The AI can reason over:

- target schema
- target constraints
- validation results
- validation evidence
- run metadata
- pipeline execution information
- summarized dataset information

The AI should not receive the complete uploaded dataset by default.

From v2.2 it also receives, bounded:

- column profiles of the uploaded file: value shapes, values that don't fit a column's usual shape (with rows), integer
  ranges and gaps, value counts for categorical columns only (never names, e-mails or keys), case-only mismatches
  with CHECK allowed values
- the uploaded rows named by failed checks, in full (at most 25); other rows are only profiled
- a snapshot of the target table taken at validation time: row count, and per column distinct count, min/max and
  value counts for categorical columns
- the run's own retry chain (the runs it retries) and what failed in each; never unrelated runs

The AI must not invent:

- row counts
- duplicate counts
- column values
- constraint definitions
- execution steps
- database errors

Factual claims should be supported by available evidence.

# 35. Core Demo Scenario

## Attempt 1 — Failure

User selects:

    Customer

Uploads:

    customer_bad.csv

Example problems:

- duplicate customer_id
- null required value
- invalid status

Result:

    FAILED_VALIDATION

Then:

    Investigate with AI

AI identifies likely causes and recommends corrections.

## Attempt 2 — Recovery

User uploads:

    customer_fixed.csv

All validations pass.

Result:

    SUCCEEDED

Example:

    100 records received
    100 records loaded
    6/6 checks passed

The visible story is:

    FAIL → INVESTIGATE → FIX → RETRY → SUCCESS

# 36. What AI Must Demonstrate

The AI portion must not be a static response.

The backend must construct the investigation context from the actual run.

The AI should demonstrate:

1. Evidence review
2. Hypothesis generation
3. Hypothesis evaluation
4. Root-cause identification
5. Evidence citation
6. Recommended remediation
7. Regression-test recommendation

Reuse the existing evidence-driven investigation implementation where possible.

# 37. What Is NOT Required for the First Implementation

Do NOT implement:

- arbitrary SQL generated by AI
- AI-generated Python execution
- automatic modification of uploaded files
- automatic correction of data
- autonomous database schema changes
- autonomous destructive database operations
- cloud-scale execution
- distributed workers
- multi-agent orchestration

The user remains responsible for correcting the input data.

# 38. API Contract Stability Rule

Once this contract is accepted:

Frontend Claude MUST NOT:

- invent backend endpoints
- change response field names
- assume database fields
- add backend behavior through frontend logic

Backend Claude MUST NOT:

- change response structures because they are easier to implement
- remove fields expected by frontend
- introduce a different upload model
- make the frontend responsible for validation

If a contract change is genuinely necessary:

    STOP
    ↓
    Explain proposed change
    ↓
    Update CONTRACT.md
    ↓
    Synchronize FE and BE
    ↓
    Continue implementation

# 39. Implementation Priority

## Milestone 1

Target database + target discovery

    GET /api/targets
    GET /api/targets/{target_id}

## Milestone 2

Single CSV upload + run creation

    POST /api/runs
    GET /api/runs/{run_id}

## Milestone 3

Target-aware deterministic validation

## Milestone 4

Transactional successful load

## Milestone 5

Run-scoped AI investigation

    POST /api/runs/{run_id}/investigate

## Milestone 6

Corrected upload/retry

    POST /api/runs/{run_id}/retry

## Milestone 7

FE integration and complete demo flow

## Milestone 8

Demo polish and presentation readiness

# 40. Existing Code Preservation

The following existing capabilities should be preserved where possible:

- AI provider abstraction
- investigation service
- structured AI response parsing
- evidence citation validation
- investigation trace
- current demo endpoints
- existing deterministic evidence concepts
- existing investigation UI
- existing test coverage

Do not rewrite working components simply to match the new architecture.

Refactor only where necessary to connect the new live run workflow.

# 41. Acceptance Criteria

The implementation is considered complete for the challenge demo when:

## Scenario A — Failure

1. Application starts.
2. User selects `customer`.
3. Target schema is displayed.
4. User uploads `customer_bad.csv`.
5. Backend creates a run.
6. Backend discovers target constraints.
7. Backend validates the uploaded CSV.
8. At least one validation fails.
9. No data is committed to the target table.
10. UI displays failed checks and evidence.
11. User clicks Investigate with AI.
12. Backend investigates actual run evidence.
13. AI returns hypotheses and root cause.
14. UI displays the investigation.
15. UI displays recommended corrective action.

## Scenario B — Recovery

16. User corrects the CSV.
17. User uploads corrected CSV using retry.
18. Backend creates a new run linked to the previous run.
19. All required validations pass.
20. Data is loaded into the target table.
21. Transaction commits.
22. Run becomes `SUCCEEDED`.
23. UI displays successful load.
24. UI displays rows loaded.
25. User can see that the failure was recovered.

The final visible story must be:

    FAILED
       ↓
    AI INVESTIGATION
       ↓
    ROOT CAUSE
       ↓
    RECOMMENDED FIX
       ↓
    CORRECTED UPLOAD
       ↓
    SUCCESS

# 42. Final Rule

This document is the authoritative FE ↔ BE contract for the challenge application.

Do not treat the old two-CSV upload contract as active.

The intended live model is:

    EXISTING TARGET TABLE
            +
       ONE CSV UPLOAD
            ↓
        VALIDATE
            ↓
       FAIL OR LOAD
            ↓
        AI INVESTIGATE
            ↓
       USER CORRECTS
            ↓
          RETRY
            ↓
         SUCCESS
