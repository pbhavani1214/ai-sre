import { useEffect, useRef, useState } from 'react';
import { Alert, Badge, Button, Card, Group, Loader, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconAlertTriangle, IconDownload, IconRefresh, IconSparkles } from '@tabler/icons-react';
import { InvestigationResult, downloadJson } from './InvestigationPanel';
import { investigateRun } from '../services/api';
import { describeInvestigationError } from '../services/errors';

/**
 * Run-scoped AI investigation: POST /api/runs/{run_id}/investigate. The backend builds the evidence from this run;
 * nothing is sent from the UI. A result already obtained for this run (kept by the parent) is shown directly.
 */
export default function RunInvestigationPanel({ runId, result, onResult }) {
  const [state, setState] = useState(result ? 'done' : 'idle');
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const timer = useRef(null);
  const inFlight = useRef(false);

  useEffect(() => () => clearInterval(timer.current), []);

  const start = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setState('running');
    setError(null);
    setElapsed(0);
    const t0 = Date.now();
    timer.current = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 250);
    try {
      onResult(await investigateRun(runId));
      setState('done');
    } catch (e) {
      setError(describeInvestigationError(e));
      setState('error');
    } finally {
      clearInterval(timer.current);
      inFlight.current = false;
    }
  };

  return (
    <Card data-testid="investigation">
      <Group justify="space-between" mb="md" gap="sm">
        <Group gap="sm">
          <ThemeIcon size="lg" variant="gradient" gradient={{ from: 'indigo', to: 'cyan' }}><IconSparkles size={18} /></ThemeIcon>
          <Title order={2} fz="lg">AI investigation</Title>
          {state === 'done' && <Badge color="green" variant="light">Complete</Badge>}
        </Group>
        {state === 'done' && result && (
          <Group gap="xs">
            <Button variant="default" size="xs" leftSection={<IconDownload size={14} />}
              onClick={() => downloadJson(result, `investigation-${runId}.json`)}>
              Download JSON
            </Button>
            <Button variant="default" size="xs" leftSection={<IconRefresh size={14} />} onClick={start}>Re-run</Button>
          </Group>
        )}
      </Group>

      {state === 'idle' && (
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            The AI reviews only this run&apos;s evidence: the target schema and constraints, the validation results and
            their evidence, and a summary of the uploaded file. It proposes hypotheses, tests them against that
            evidence, and recommends a fix. Nothing is changed automatically.
          </Text>
          <Group>
            <Button leftSection={<IconSparkles size={18} />} onClick={start}>Investigate with AI</Button>
          </Group>
        </Stack>
      )}

      {state === 'running' && (
        <Group gap="sm" aria-live="polite">
          <Loader size="sm" />
          <div>
            <Text size="sm" fw={500}>Investigating this run…</Text>
            <Text size="xs" c="dimmed">{elapsed}s elapsed. This usually takes under a minute.</Text>
          </div>
        </Group>
      )}

      {state === 'error' && error && (
        <Alert color="red" variant="light" icon={<IconAlertTriangle />} title={error.title} role="alert">
          {error.message && <Text size="sm">{error.message}</Text>}
          {error.hint && <Text size="sm" c="dimmed" mt={4}>{error.hint}</Text>}
          {error.retryable && (
            <Button mt="sm" size="xs" color="red" variant="light" leftSection={<IconRefresh size={14} />} onClick={start}>
              Try again
            </Button>
          )}
        </Alert>
      )}

      {state === 'done' && result && <InvestigationResult result={result} reasoningOpen />}
    </Card>
  );
}
