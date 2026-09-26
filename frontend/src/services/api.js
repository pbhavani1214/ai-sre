import scenarioMock from '../data/scenario.json';
import investigationMock from '../data/investigation.mock.json';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

/** True when no backend is configured and the UI runs on bundled sample data. */
export const USE_MOCK = !BASE_URL;

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

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
    throw new Error(`Request failed (${res.status}). ${body.slice(0, 300)}`);
  }
  return res.json();
}

/** @returns {Promise<import('../types').Scenario>} */
export async function getScenario() {
  if (USE_MOCK) {
    await delay(300);
    return scenarioMock;
  }
  return request('/api/scenario');
}

/** @returns {Promise<import('../types').InvestigationResult>} */
export async function runInvestigation() {
  if (USE_MOCK) {
    await delay(3500);
    return investigationMock;
  }
  return request('/api/investigations', { method: 'POST', body: '{}' });
}
