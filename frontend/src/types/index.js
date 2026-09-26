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
 * @typedef {Object} Health  GET /health
 * @property {'ok'} status
 * @property {boolean} llm_configured
 * @property {Object<string, any>} details
 */
export {};
