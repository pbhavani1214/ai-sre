import { useEffect, useState } from 'react';
import { getHealth } from '../services/api';

/** status: 'mock' | 'checking' | 'ready' | 'no-llm' | 'offline' */
export function useHealth() {
  const [state, setState] = useState({ status: 'checking', details: null });

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (cancelled) return;
        if (!h) setState({ status: 'mock', details: null });
        else setState({ status: h.llm_configured ? 'ready' : 'no-llm', details: h.details });
      })
      .catch((e) => !cancelled && setState({ status: 'offline', details: { error: e.message } }));
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
