import scenarioMock from '../data/scenario.json';
import investigationMock from '../data/investigation.mock.json';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

/** True when no backend is configured and the UI runs on bundled sample data. */
export const USE_MOCK = !BASE_URL;

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

/** An HTTP or network error, keeping the structured fields of `{detail: {code, message, field}}`. */
export class ApiError extends Error {
  constructor(message, { status = null, code = null, field = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

/**
 * FastAPI errors come in three forms: `{detail: string}`, the structured form used by the live endpoints
 * `{detail: {code, message, field}}`, and request validation errors `{detail: [{msg, loc}]}`.
 */
function parseError(status, body) {
  let detail;
  try {
    ({ detail } = JSON.parse(body));
  } catch {
    return new ApiError(`Request failed (${status}).`, { status });
  }
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    return new ApiError(detail.message || `Request failed (${status}).`, {
      status, code: detail.code ?? null, field: detail.field ?? null,
    });
  }
  const text = Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : String(detail ?? '');
  return new ApiError(`Request failed (${status}). ${text}`.trim(), { status });
}

async function request(path, options = {}) {
  const { json, ...rest } = options;
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...(json !== undefined && { headers: { 'content-type': 'application/json' }, body: JSON.stringify(json) }),
      ...rest,
    });
  } catch {
    throw new ApiError(`Could not reach the backend at ${BASE_URL}. Is it running?`, { code: 'network_error' });
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw parseError(res.status, body);
  }
  try {
    return await res.json();
  } catch {
    throw new ApiError('The backend returned a response that is not JSON.', { status: res.status, code: 'invalid_response' });
  }
}

/** The live flow never falls back to bundled data: without a backend it fails with a clear error. */
function requireBackend() {
  if (USE_MOCK) {
    throw new ApiError('No backend is configured. Set VITE_API_BASE_URL (for example http://localhost:8000).', {
      code: 'backend_not_configured',
    });
  }
}

/** @returns {Promise<import('../types').TargetSummary[]>} */
export async function listTargets() {
  requireBackend();
  const { targets } = await request('/api/targets');
  return targets;
}

/** @returns {Promise<import('../types').TargetDetail>} */
export async function getTarget(targetId) {
  requireBackend();
  return request(`/api/targets/${encodeURIComponent(targetId)}`);
}

/**
 * POST /api/runs: creates a run from ONE uploaded CSV for the selected target (multipart/form-data).
 * Sends exactly `target_id` and `file`. The backend owns validation.
 * @param {string} targetId
 * @param {File} file
 * @returns {Promise<import('../types').RunSummary>}
 */
export async function createRun(targetId, file) {
  requireBackend();
  const form = new FormData();
  form.append('target_id', targetId);
  form.append('file', file);
  // No content-type header: the browser sets multipart/form-data with its boundary.
  return request('/api/runs', { method: 'POST', body: form });
}

/**
 * The demo run: the deterministic validation state plus the raw run record and datasets.
 * @returns {Promise<import('../types').Scenario>}
 */
export async function getScenario() {
  if (USE_MOCK) {
    await delay(300);
    return scenarioMock;
  }
  const [scenario, run] = await Promise.all([request('/api/demo/scenario'), request('/api/demo/run')]);
  return { ...scenario, ...run };
}

/** @returns {Promise<import('../types').Health | null>} null in mock mode */
export async function getHealth() {
  if (USE_MOCK) return null;
  return request('/health');
}

/**
 * Asks the backend to investigate the demo run. The backend re-runs the validation suite on the
 * bundled data itself (use_demo_data), so the AI sees exactly the evidence shown in the UI.
 * @param {import('../types').Scenario} scenario
 * @returns {Promise<import('../types').InvestigationResult>}
 */
export async function runInvestigation(scenario) {
  if (USE_MOCK) {
    await delay(3500);
    return investigationMock;
  }
  return request('/api/investigate', {
    method: 'POST',
    json: {
      pipeline_name: scenario.pipeline_name,
      pipeline_description: scenario.pipeline_description,
      execution_summary: scenario.execution_summary,
      use_demo_data: true,
    },
  });
}
