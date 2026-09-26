import scenarioMock from '../data/scenario.json';
import investigationMock from '../data/investigation.mock.json';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

/** True when no backend is configured and the UI runs on bundled sample data. */
export const USE_MOCK = !BASE_URL;

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

/** FastAPI errors are `{detail: string}` or, for validation errors, `{detail: [{msg, loc}]}`. */
function errorDetail(body) {
  try {
    const { detail } = JSON.parse(body);
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ');
  } catch {
    // not JSON
  }
  return body.slice(0, 300);
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      headers: { 'content-type': 'application/json' },
      ...options,
    });
  } catch {
    throw new Error(`Could not reach the backend at ${BASE_URL}. Is it running?`);
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`Request failed (${res.status}). ${errorDetail(body)}`);
  }
  return res.json();
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
    body: JSON.stringify({
      pipeline_name: scenario.pipeline_name,
      pipeline_description: scenario.pipeline_description,
      execution_summary: scenario.execution_summary,
      use_demo_data: true,
    }),
  });
}
