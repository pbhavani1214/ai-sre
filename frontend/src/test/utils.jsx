import { render } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { vi } from 'vitest';
import { theme } from '../theme';

export function renderWithMantine(ui) {
  return render(<MantineProvider theme={theme} env="test">{ui}</MantineProvider>);
}

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

/**
 * Mocks fetch with a map of "METHOD path" -> handler. A handler returns [status, body], a Response,
 * a Promise of either (to hold a request open), or throws to simulate a network failure.
 */
export function mockFetch(routes) {
  const fn = vi.fn(async (url, init = {}) => {
    const { pathname } = new URL(url);
    const key = `${init.method ?? 'GET'} ${pathname}`;
    const handler = routes[key];
    if (!handler) return json(500, { detail: `No mock for ${key}` });
    const out = await handler();
    return out instanceof Response ? out : json(out[0], out[1]);
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

/** A promise you resolve later, to observe loading states. */
export function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}
