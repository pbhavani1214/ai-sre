const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

/** True when VITE_API_BASE_URL is not set. The app needs the backend; there is no offline or sample-data mode. */
export const USE_MOCK = !BASE_URL;

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

/** GET /api/databases: the SQLite databases a user can choose from (the default one first). */
export async function listDatabases() {
  requireBackend();
  const { databases } = await request('/api/databases');
  return databases;
}

const withDatabase = (path, databaseId) => (databaseId ? `${path}?database_id=${encodeURIComponent(databaseId)}` : path);

/** GET /api/targets?database_id=: the tables of one database. @returns {Promise<import('../types').TargetSummary[]>} */
export async function listTargets(databaseId) {
  requireBackend();
  const { targets } = await request(withDatabase('/api/targets', databaseId));
  return targets;
}

/** @returns {Promise<import('../types').TargetDetail>} */
export async function getTarget(targetId, databaseId) {
  requireBackend();
  return request(withDatabase(`/api/targets/${encodeURIComponent(targetId)}`, databaseId));
}

/**
 * POST /api/runs: creates a run from ONE uploaded CSV for the selected target (multipart/form-data).
 * Sends `target_id`, `file` and, when a database was chosen, `database_id`. The backend owns validation.
 * @param {string} targetId
 * @param {File} file
 * @param {string} [databaseId]
 * @returns {Promise<import('../types').RunSummary>}
 */
export async function createRun(targetId, file, databaseId) {
  requireBackend();
  const form = new FormData();
  form.append('target_id', targetId);
  form.append('file', file);
  if (databaseId) form.append('database_id', databaseId);
  // No content-type header: the browser sets multipart/form-data with its boundary.
  return request('/api/runs', { method: 'POST', body: form });
}

/** GET /api/runs/{run_id}: the stored RunSummary (used to show a retry's parent run). */
export async function getRun(runId) {
  requireBackend();
  return request(`/api/runs/${encodeURIComponent(runId)}`);
}

/**
 * POST /api/runs/{run_id}/investigate: run-scoped AI investigation. No body; the backend builds the evidence
 * from the stored run.
 * @returns {Promise<import('../types').RunInvestigation>}
 */
export async function investigateRun(runId) {
  requireBackend();
  return request(`/api/runs/${encodeURIComponent(runId)}/investigate`, { method: 'POST' });
}

/**
 * POST /api/runs/{run_id}/retry: a NEW run from a corrected CSV, linked by parent_run_id. The original run is
 * left unchanged. Sends exactly one field, `file`.
 * @returns {Promise<import('../types').RunSummary>}
 */
export async function retryRun(runId, file) {
  requireBackend();
  const form = new FormData();
  form.append('file', file);
  return request(`/api/runs/${encodeURIComponent(runId)}/retry`, { method: 'POST', body: form });
}

/**
 * GET /api/runs/{run_id}/suggested-csv: the uploaded file with the investigation's REPLACE and DELETE_ROW fixes applied
 * (CONTRACT.md §16, v2.2). Returns the CSV text. Nothing is validated until the file is retried.
 * @returns {Promise<string>}
 */
export async function getSuggestedCsv(runId) {
  requireBackend();
  let res;
  try {
    res = await fetch(`${BASE_URL}/api/runs/${encodeURIComponent(runId)}/suggested-csv`);
  } catch {
    throw new ApiError(`Could not reach the backend at ${BASE_URL}. Is it running?`, { code: 'network_error' });
  }
  if (!res.ok) throw parseError(res.status, await res.text().catch(() => ''));
  return res.text();
}

/** @returns {Promise<import('../types').Health | null>} null when no backend is configured */
export async function getHealth() {
  if (USE_MOCK) return null;
  return request('/health');
}
