import { useCallback, useEffect, useRef, useState } from 'react';
import { runInvestigation } from '../services/api';

/** status: 'idle' | 'running' | 'done' | 'error' */
export function useInvestigation() {
  const [status, setStatus] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const timer = useRef(null);

  useEffect(() => () => clearInterval(timer.current), []);

  const start = useCallback(async (scenario) => {
    setStatus('running');
    setError(null);
    setElapsed(0);
    const t0 = Date.now();
    clearInterval(timer.current);
    timer.current = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 250);
    try {
      setResult(await runInvestigation(scenario));
      setStatus('done');
    } catch (e) {
      setError(e);
      setStatus('error');
    } finally {
      clearInterval(timer.current);
    }
  }, []);

  return { status, result, error, elapsed, start };
}
