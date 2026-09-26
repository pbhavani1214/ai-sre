/**
 * Shapes of the JSON exchanged with the backend. They mirror the Pydantic models in
 * src/api/schemas.py (the source of truth for the contract).
 *
 * @typedef {Object} Hypothesis
 * @property {string} hypothesis
 * @property {'SUPPORTED'|'REJECTED'|'INCONCLUSIVE'} status
 * @property {string[]} evidence   "[evidence.id] observation" lines
 * @property {string} reasoning
 *
 * @typedef {Object} InvestigationResult  AI investigation (the shape of POST /api/runs/{run_id}/investigate)
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
 * @typedef {Object} DatabaseSummary  one entry of GET /api/databases -> {databases: DatabaseSummary[]} (§5a)
 * @property {string} database_id     stable ID used in API calls; never build file paths from it
 * @property {string} display_name
 * @property {string} file_name
 * @property {string} database_type   "sqlite"
 * @property {number} table_count
 * @property {boolean} is_default
 *
 * @typedef {Object} TargetSummary  one entry of GET /api/targets?database_id= -> {targets: TargetSummary[]}
 * @property {string} target_id       stable ID used in API calls; never build table names from it
 * @property {string} table_name      the actual database table
 * @property {string} display_name
 * @property {string} [description]
 * @property {string} database_type   "sqlite"
 * @property {string} database_id
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
 * @property {string} database_id
 * @property {TargetColumn[]} columns
 * @property {TargetConstraint[]} constraints
 *
 * --- Live flow: runs (AI_SRE_CONTRACT_v2 §11-15) ---
 *
 * @typedef {'CREATED'|'VALIDATING'|'FAILED_VALIDATION'|'LOADING'|'SUCCEEDED'|'LOAD_FAILED'} RunStatus
 *
 * @typedef {Object} RunCounts  RunSummary.summary
 * @property {number} rows_received
 * @property {number} checks_total
 * @property {number} checks_passed
 * @property {number} checks_failed
 *
 * @typedef {Object} RunValidationResult  one entry of RunSummary.validation_results (CONTRACT.md §9)
 * @property {string} name               e.g. "primary_key_uniqueness"; any name the backend defines
 * @property {'PASSED'|'FAILED'|'WARNING'|'SKIPPED'} status
 * @property {'INFO'|'WARNING'|'ERROR'} severity
 * @property {string} summary            human-readable message
 * @property {Object<string, any>} metrics
 * @property {string[]} evidence         deterministic lines from the backend, shown verbatim
 *
 * @typedef {Object} RunSummary  POST /api/runs (201), GET /api/runs/{run_id}
 * @property {string} run_id
 * @property {string|null} parent_run_id
 * @property {string} database_id     the database the target belongs to (a retry inherits its parent's)
 * @property {string} target_id
 * @property {string} target_table
 * @property {string} file_name
 * @property {RunStatus} status
 * @property {string} created_at
 * @property {string|null} completed_at
 * @property {RunCounts} summary
 * @property {RunValidationResult[]} validation_results
 * @property {Object<string, any> | null} load_result   CONTRACT.md §14/§22: {rows_loaded, target_table}; rendered
 *                                                     generically so any fields the backend adds are shown
 *
 * @typedef {InvestigationResult & {run_id: string}} RunInvestigation  POST /api/runs/{run_id}/investigate (§16)
 *
 * @typedef {Object} Health  GET /health
 * @property {'ok'} status
 * @property {boolean} llm_configured
 * @property {Object<string, any>} details
 */
export {};
