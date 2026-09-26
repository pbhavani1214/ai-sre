/**
 * Shapes of the JSON exchanged with the backend. They mirror the Python models in
 * src/validation/tools.py (ValidationResult) and src/investigation/models.py
 * (InvestigationResult.to_dict()).
 *
 * @typedef {Object} ValidationResult
 * @property {string} check
 * @property {boolean} passed
 * @property {string} summary
 * @property {Object<string, any>} details
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
 * @typedef {Object} Scenario
 * @property {string} pipeline_description
 * @property {Object<string, any>[]} source
 * @property {Object<string, any>[]} target
 * @property {PipelineRun} pipeline_run
 * @property {ValidationResult[]} validation_results
 *
 * @typedef {Object} Hypothesis
 * @property {string} statement
 * @property {'confirmed'|'rejected'|'inconclusive'|string} status
 * @property {number} confidence 0..1
 * @property {string[]} supporting_evidence
 * @property {string[]} contradicting_evidence
 *
 * @typedef {Object} InvestigationResult
 * @property {string} summary
 * @property {Hypothesis[]} hypotheses
 * @property {{source: string, observation: string}[]} evidence
 * @property {string} root_cause
 * @property {string} recommended_fix
 * @property {{name: string, description: string, code: string}} regression_test
 */
export {};
