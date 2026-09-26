import { useCallback, useEffect, useState } from 'react';
import { getScenario } from '../services/api';

export function useScenario() {
  const [state, setState] = useState({ data: null, error: null, loading: true });

  const load = useCallback(() => {
    setState({ data: null, error: null, loading: true });
    getScenario()
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }));
  }, []);

  useEffect(load, [load]);
  return { ...state, reload: load };
}
