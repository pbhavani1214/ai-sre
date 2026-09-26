"""AI investigation of a failed upload run, using only the evidence that run produced.

Reuses the investigation service unchanged (same prompt, citation checks and result format);
this module only assembles the run's evidence package.
"""

from __future__ import annotations

from typing import Any

from src.ai.provider import LLMProvider
from src.investigation.models import InvestigationResult
from src.investigation.service import investigate_evidence
from src.runs.store import RunRecord

DESCRIPTION = (
    "A user uploaded the file {file_name} to be loaded into the existing SQLite table {table}. "
    "The load pipeline parses the CSV as text, checks the file's columns against the table's columns, "
    "validates every row against the table's own rules (NOT NULL, column types, PRIMARY KEY and UNIQUE "
    "keys, both within the file and against rows already in the table, and every CHECK constraint in "
    "the DDL), and loads all rows in one transaction only if every check passes. The load is "
    "all-or-nothing: if anything fails, no rows are written. The table definition, including its DDL, "
    "is in target_table. Line numbers in the evidence are line numbers in the uploaded file "
    "(line 1 is the header). The fix is applied by the user correcting the file and uploading it again."
)


def build_run_context(record: RunRecord) -> dict[str, Any]:
    d = record.detail
    target = {k: record.target[k] for k in
              ("name", "ddl", "row_count", "columns", "primary_key", "unique_keys", "check_constraints")}
    return {
        "pipeline_name": f"Load {d['file_name']} into {d['target_table']}",
        "pipeline_description": DESCRIPTION.format(file_name=d["file_name"], table=d["target_table"]),
        "execution_evidence": {
            "execution_summary": {
                "run_status": d["status"],
                "failed_stage": d["failed_stage"],
                "target_table": d["target_table"],
                "file_name": d["file_name"],
                "upload_rows": d["row_count"],
                "rows_loaded": d["rows_loaded"],
                "target_rows_before": d["target_rows_before"],
                "target_rows_after": d["target_rows_after"],
                "load_error": d["load_error"],
                "retry_of": d["retry_of"],
                "retry_comparison": d["retry_comparison"],
            },
            "pipeline_run": d["pipeline_run"],
        },
        "validation_results": d["validation_results"],
        "target_table": target,
        "upload": record.upload_profile,
    }


def investigate_run(record: RunRecord, provider: LLMProvider | None = None) -> InvestigationResult:
    return investigate_evidence(build_run_context(record), provider)
