/**
 * Shapes of the JSON exchanged with the backend. They mirror the Pydantic models in
 * src/api/schemas.py (the source of truth for the contract).
 *
 * @typedef {Object} CheckResult  one entry of GET /api/demo/scenario validation_results
 * @property {string} name        e.g. "duplicate_customer_id"
 * @property {'PASSED'|'FAILED'} status
 * @property {'HIGH'|'MEDIUM'|'LOW'} severity
 * @property {string} summary
 * @property {Object<string, any>} metrics   numbers, or id/value -> count maps
 * @property {string[]} evidence             human-readable lines (capped by the backend)
 *
 * @typedef {Object} PipelineStep
 * @property {string} name
 * @property {string} status
 * @property {number} rows_in
 * @property {number} [rows_out]
 * @property {number} [rows_written]
 * @property {number} [batches]
 * @property {string[]} [warnings]
 *
 * @typedef {Object} PipelineRun
 * @property {string} run_id
 * @property {string} pipeline
 * @property {string} started_at
 * @property {string} finished_at
 * @property {string} status
 * @property {Object<string, any>} config
 * @property {PipelineStep[]} steps
 * @property {string[]} logs
 *
 * @typedef {Object} ExecutionSummary
 * @property {number} source_records
 * @property {number} target_records
 * @property {string} [run_id]
 * @property {string} [reported_run_status]
 * @property {string} [started_at]
 * @property {string} [finished_at]
 *
 * @typedef {Object} Scenario  GET /api/demo/scenario merged with GET /api/demo/run
 * @property {string} pipeline_name
 * @property {string} pipeline_description
 * @property {'PASSED'|'FAILED'} status
 * @property {ExecutionSummary} execution_summary
 * @property {{total_checks: number, passed_checks: number, failed_checks: number}} validation_summary
 * @property {CheckResult[]} validation_results
 * @property {PipelineRun} pipeline_run
 * @property {Object<string, any>[]} source
 * @property {Object<string, any>[]} target
 *
 * @typedef {Object} Hypothesis
 * @property {string} hypothesis
 * @property {'SUPPORTED'|'REJECTED'|'INCONCLUSIVE'} status
 * @property {string[]} evidence   "[evidence.id] observation" lines
 * @property {string} reasoning
 *
 * @typedef {Object} InvestigationResult  POST /api/investigate
 * @property {string} summary
 * @property {string[]} observed_facts
 * @property {Hypothesis[]} hypotheses
 * @property {'IDENTIFIED'|'INCONCLUSIVE'} root_cause_status
 * @property {string} root_cause
 * @property {string[]} root_cause_evidence
 * @property {string} root_cause_reasoning
 * @property {string[]} evidence   alias of observed_facts
 * @property {string} recommended_fix
 * @property {string} regression_test   Python source (never executed)
 * @property {{stage: string, description: string}[]} investigation_trace
 * @property {string[]} evidence_warnings
 *
 * --- Live flow: target tables (AI_SRE_CONTRACT_v2 §6-7) ---
 *
 * @typedef {Object} TargetSummary  one entry of GET /api/targets -> {targets: TargetSummary[]}
 * @property {string} target_id       stable ID used in API calls; never build table names from it
 * @property {string} table_name      the actual database table
 * @property {string} display_name
 * @property {string} [description]
 * @property {string} database_type   "sqlite"
 *
 * @typedef {Object} TargetColumn
 * @property {string} name
 * @property {string} data_type       e.g. "INTEGER", "TEXT"
 * @property {boolean} nullable
 * @property {boolean} primary_key
 * @property {boolean} unique
 *
 * @typedef {Object} TargetConstraint
 * @property {string} type            "PRIMARY_KEY" | "UNIQUE" | "NOT_NULL" | "CHECK" (others possible)
 * @property {string[]} columns
 * @property {string[]} [allowed_values]   CHECK constraints listing their allowed values
 * @property {string} description
 *
 * @typedef {Object} TargetDetail  GET /api/targets/{target_id}
 * @property {string} target_id
 * @property {string} table_name
 * @property {string} database_type
 * @property {TargetColumn[]} columns
 * @property {TargetConstraint[]} constraints
 *
 * --- Live flow: runs (AI_SRE_CONTRACT_v2 §11-15) ---
 *
 * @typedef {'CREATED'|'VALIDATING'|'FAILED_VALIDATION'|'LOADING'|'SUCCEEDED'|'LOAD_FAILED'} RunStatus
 *
 * @typedef {Object} RunSummary  POST /api/runs (201), GET /api/runs/{run_id}
 * @property {string} run_id
 * @property {string|null} parent_run_id
 * @property {string} target_id
 * @property {string} target_table
 * @property {string} file_name
 * @property {RunStatus} status
 * @property {string} created_at
 * @property {string|null} completed_at
 * @property {{rows_received: number, checks_total: number, checks_passed: number, checks_failed: number}} summary
 * @property {Object[]} validation_results   rendered in a later milestone
 * @property {{rows_loaded: number, target_table: string} | null} load_result
 *
 * @typedef {Object} Health  GET /health
 * @property {'ok'} status
 * @property {boolean} llm_configured
 * @property {Object<string, any>} details
 */
export {};
