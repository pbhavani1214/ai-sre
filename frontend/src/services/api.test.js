import { describe, expect, it, vi } from 'vitest';
import { ApiError, getTarget, listTargets } from './api';
import { mockFetch } from '../test/utils';

describe('target API client', () => {
  it('listTargets unwraps {targets} from GET /api/targets', async () => {
    mockFetch({ 'GET /api/targets': () => [200, { targets: [{ target_id: 't1' }] }] });
    await expect(listTargets()).resolves.toEqual([{ target_id: 't1' }]);
  });

  it('getTarget encodes the target_id', async () => {
    const fetch = mockFetch({ 'GET /api/targets/a%20b': () => [200, { target_id: 'a b' }] });
    await getTarget('a b');
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/targets/a%20b', expect.anything());
  });

  it('turns the structured error form into an ApiError with code, field and message', async () => {
    mockFetch({
      'GET /api/targets/x': () => [404, { detail: { code: 'target_not_found', message: "Target 'x' was not found.", field: 'target_id' } }],
    });
    const err = await getTarget('x').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: 'target_not_found', field: 'target_id', message: "Target 'x' was not found." });
  });

  it('never shows a raw non-JSON error body', async () => {
    mockFetch({ 'GET /api/targets': () => new Response('Traceback (most recent call last): ...', { status: 500 }) });
    const err = await listTargets().catch((e) => e);
    expect(err.message).toBe('Request failed (500).');
  });

  it('reports a non-JSON success response as an error', async () => {
    mockFetch({ 'GET /api/targets': () => new Response('<!doctype html>', { status: 200 }) });
    await expect(listTargets()).rejects.toMatchObject({ code: 'invalid_response' });
  });

  it('refuses to run the live flow without a configured backend (no mock fallback)', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    vi.resetModules();
    const fetch = mockFetch({});
    const api = await import('./api');
    await expect(api.listTargets()).rejects.toMatchObject({ code: 'backend_not_configured' });
    expect(fetch).not.toHaveBeenCalled();
    vi.unstubAllEnvs();
  });
});
