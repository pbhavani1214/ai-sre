import { useCallback, useEffect, useState } from 'react';
import { getTarget, listTargets } from '../services/api';

/** GET /api/targets. */
export function useTargets() {
  const [state, setState] = useState({ data: null, error: null, loading: true });

  const load = useCallback(() => {
    let cancelled = false;
    setState({ data: null, error: null, loading: true });
    listTargets()
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setState({ data: null, error, loading: false }));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(load, [load]);
  return { ...state, reload: load };
}

/** GET /api/targets/{target_id} for the selected target. Responses for an earlier selection are ignored. */
export function useTargetDetail(targetId) {
  const [state, setState] = useState({ data: null, error: null, loading: false });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!targetId) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }
    let cancelled = false;
    setState({ data: null, error: null, loading: true });
    getTarget(targetId)
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setState({ data: null, error, loading: false }));
    return () => {
      cancelled = true;
    };
  }, [targetId, attempt]);

  return { ...state, reload: () => setAttempt((n) => n + 1) };
}
