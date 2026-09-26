import { useCallback, useEffect, useState } from 'react';
import { getTarget, listDatabases, listTargets } from '../services/api';

/**
 * Runs `load` whenever `key` changes (nothing while `key` is null) and ignores responses for an earlier key.
 * Returns {data, error, loading, reload}.
 */
function useLoad(load, key) {
  const [state, setState] = useState({ data: null, error: null, loading: key !== null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (key === null) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }
    let cancelled = false;
    setState({ data: null, error: null, loading: true });
    load()
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setState({ data: null, error, loading: false }));
    return () => {
      cancelled = true;
    };
    // `load` closes over the same values `key` encodes.
  }, [key, attempt]);

  return { ...state, reload: useCallback(() => setAttempt((n) => n + 1), []) };
}

/** GET /api/databases. */
export function useDatabases() {
  return useLoad(listDatabases, 'databases');
}

/** GET /api/targets?database_id= for the chosen database (nothing until one is chosen). */
export function useTargets(databaseId) {
  return useLoad(() => listTargets(databaseId), databaseId ?? null);
}

/** GET /api/targets/{target_id}?database_id= for the selected table. */
export function useTargetDetail(targetId, databaseId) {
  return useLoad(() => getTarget(targetId, databaseId), targetId && databaseId ? `${databaseId}/${targetId}` : null);
}
