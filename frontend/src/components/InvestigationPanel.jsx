import {
  Alert, Badge, Button, Card, Code, Group, List, Loader, Paper, SimpleGrid, Spoiler, Stack, Tabs, Text, ThemeIcon, Timeline, Title,
} from '@mantine/core';
import {
  IconAlertTriangle, IconBulb, IconCheck, IconDownload, IconFlask, IconListSearch, IconRefresh, IconRoute,
  IconSearch, IconSparkles, IconTarget,
} from '@tabler/icons-react';
import HypothesisList from './HypothesisList';
import CodeBlock from './CodeBlock';
import CitedList from './CitedList';
import { humanize, isFailed } from '../utils';
import { useHealth } from '../hooks/useHealth';

function StepRow({ state, title, detail }) {
  const icon =
    state === 'done' ? (
      <ThemeIcon color="green" radius="xl" size={26}><IconCheck size={16} /></ThemeIcon>
    ) : state === 'active' ? (
      <ThemeIcon color="indigo" variant="light" radius="xl" size={26}><Loader size={14} /></ThemeIcon>
    ) : (
      <ThemeIcon color="gray" variant="light" radius="xl" size={26}><Text size="xs">•</Text></ThemeIcon>
    );
  return (
    <Group gap="sm" wrap="nowrap" align="flex-start">
      {icon}
      <div>
        <Text size="sm" fw={500} c={state === 'pending' ? 'dimmed' : undefined}>{title}</Text>
        {detail && <Text size="xs" c="dimmed">{detail}</Text>}
      </div>
    </Group>
  );
}

function Idle({ validations, onStart }) {
  const failed = validations.filter(isFailed).length;
  const health = useHealth();
  return (
    <Stack gap="md">
      {health.status === 'no-llm' && (
        <Alert color="yellow" variant="light" icon={<IconAlertTriangle />} title="The backend has no AI provider configured">
          Set <Code>LLM_API_KEY</Code> in the backend&apos;s <Code>.env</Code> and restart it, or the investigation will fail.
        </Alert>
      )}
      <Text size="sm" c="dimmed">
        The AI reads only the evidence gathered from this run: validation results, summaries of the source and
        target data (row counts, columns, nulls), and the pipeline&apos;s config, steps and logs. It forms competing hypotheses, tests each against that evidence, and
        suggests a fix. Nothing is hardcoded and no generated code is executed.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        {[
          { icon: IconListSearch, t: '1. Evidence', d: `${validations.length} checks ready (${failed} failed), plus run logs` },
          { icon: IconSearch, t: '2. Hypotheses', d: 'Each is supported or rejected against the evidence' },
          { icon: IconTarget, t: '3. Root cause & fix', d: 'With a regression test you can copy' },
        ].map((s) => (
          <Paper key={s.t} withBorder p="sm" radius="md">
            <Group gap="sm" wrap="nowrap">
              <ThemeIcon variant="light" size="lg"><s.icon size={18} /></ThemeIcon>
              <div>
                <Text size="sm" fw={600}>{s.t}</Text>
                <Text size="xs" c="dimmed">{s.d}</Text>
              </div>
            </Group>
          </Paper>
        ))}
      </SimpleGrid>
      <Group>
        <Button leftSection={<IconSparkles size={18} />} onClick={onStart}>Start investigation</Button>
      </Group>
    </Stack>
  );
}

function Running({ elapsed, validations }) {
  return (
    <Stack gap="md" aria-live="polite">
      <StepRow state="done" title="Evidence collected" detail={`${validations.length} validation checks, data profiles, run config, steps and logs`} />
      <StepRow state="active" title="AI is analysing the evidence…" detail={`${elapsed}s elapsed. This usually takes under a minute.`} />
      <StepRow state="pending" title="Structuring the result" />
    </Stack>
  );
}

export function downloadJson(result, fileName = 'investigation.json') {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: fileName });
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * An InvestigateResponse (demo and run-scoped investigations share the shape). With `reasoningOpen`, the root-cause
 * reasoning and evidence are shown directly instead of behind "Why?".
 */
export function InvestigationResult({ result: raw, reasoningOpen = false }) {
  const result = {
    ...raw,
    hypotheses: raw.hypotheses ?? [], observed_facts: raw.observed_facts ?? [], root_cause_evidence: raw.root_cause_evidence ?? [],
    investigation_trace: raw.investigation_trace ?? [], evidence_warnings: raw.evidence_warnings ?? [],
  };
  const supported = result.hypotheses.filter((h) => h.status === 'SUPPORTED').length;
  const identified = result.root_cause_status === 'IDENTIFIED';
  return (
    <Stack gap="lg">
      <Text>{result.summary}</Text>

      {result.evidence_warnings.length > 0 && (
        <Alert color="yellow" variant="light" icon={<IconAlertTriangle />} title="Check these citations">
          <List size="sm" spacing={4}>
            {result.evidence_warnings.map((w, i) => <List.Item key={i}>{w}</List.Item>)}
          </List>
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Paper withBorder p="md" radius="md" style={{ borderLeft: '4px solid var(--mantine-color-red-6)' }}>
          <Group gap="xs" mb="xs">
            <ThemeIcon color="red" variant="light"><IconTarget size={16} /></ThemeIcon>
            <Text fw={600}>Root cause</Text>
            <Badge size="sm" variant="light" color={identified ? 'red' : 'yellow'}>
              {identified ? 'Identified' : 'Inconclusive'}
            </Badge>
          </Group>
          <Text size="sm" style={{ whiteSpace: 'pre-line' }}>{result.root_cause}</Text>
          {reasoningOpen ? (
            <Stack gap="sm" mt="sm">
              <div>
                <Text size="xs" fw={600} tt="uppercase" c="dimmed" mb={4}>Root cause reasoning</Text>
                <Text size="sm" style={{ whiteSpace: 'pre-line' }}>{result.root_cause_reasoning}</Text>
              </div>
              <div>
                <Text size="xs" fw={600} tt="uppercase" c="dimmed" mb={4}>Root cause evidence</Text>
                <CitedList items={result.root_cause_evidence} />
              </div>
            </Stack>
          ) : (
            <Spoiler maxHeight={0} showLabel="Why?" hideLabel="Hide reasoning" mt="xs">
              <Stack gap="sm" pt={4}>
                <Text size="sm" c="dimmed" style={{ whiteSpace: 'pre-line' }}>{result.root_cause_reasoning}</Text>
                <CitedList items={result.root_cause_evidence} />
              </Stack>
            </Spoiler>
          )}
        </Paper>
        <Paper withBorder p="md" radius="md" style={{ borderLeft: '4px solid var(--mantine-color-green-6)' }}>
          <Group gap="xs" mb="xs">
            <ThemeIcon color="green" variant="light"><IconBulb size={16} /></ThemeIcon>
            <Text fw={600}>Recommended fix</Text>
          </Group>
          <Text size="sm" style={{ whiteSpace: 'pre-line' }}>{result.recommended_fix}</Text>
        </Paper>
      </SimpleGrid>

      <Tabs defaultValue="hypotheses" keepMounted={false}>
        <Tabs.List className="scroll-tabs">
          <Tabs.Tab value="hypotheses" leftSection={<IconSearch size={16} />}>
            Hypotheses <Badge size="xs" variant="light" ml={4}>{supported}/{result.hypotheses.length}</Badge>
          </Tabs.Tab>
          <Tabs.Tab value="facts" leftSection={<IconListSearch size={16} />}>
            Observed facts <Badge size="xs" variant="light" color="gray" ml={4}>{result.observed_facts.length}</Badge>
          </Tabs.Tab>
          <Tabs.Tab value="trace" leftSection={<IconRoute size={16} />}>Trace</Tabs.Tab>
          <Tabs.Tab value="test" leftSection={<IconFlask size={16} />}>Regression test</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="hypotheses" pt="md">
          <HypothesisList hypotheses={result.hypotheses} />
        </Tabs.Panel>

        <Tabs.Panel value="facts" pt="md">
          <CitedList items={result.observed_facts} empty="No facts reported." />
        </Tabs.Panel>

        <Tabs.Panel value="trace" pt="md">
          <Timeline bulletSize={22} lineWidth={2} active={result.investigation_trace.length}>
            {result.investigation_trace.map((t) => (
              <Timeline.Item key={t.stage} title={<Text size="sm" fw={600}>{humanize(t.stage)}</Text>}>
                <Text size="sm" c="dimmed">{t.description}</Text>
              </Timeline.Item>
            ))}
          </Timeline>
        </Tabs.Panel>

        <Tabs.Panel value="test" pt="md">
          <Stack gap="sm">
            <CodeBlock code={result.regression_test} />
            <Text size="xs" c="dimmed">Generated by the AI for review. This system never executes generated code.</Text>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

export default function InvestigationPanel({ status, result, error, elapsed, validations, onStart }) {
  return (
    <Card>
      <Group justify="space-between" mb="md" gap="sm">
        <Group gap="sm">
          <ThemeIcon size="lg" variant="gradient" gradient={{ from: 'indigo', to: 'cyan' }}>
            <IconSparkles size={18} />
          </ThemeIcon>
          <Title order={3} fz="lg">AI investigation</Title>
          {status === 'done' && <Badge color="green" variant="light">Complete</Badge>}
        </Group>
        {status === 'done' && (
          <Group gap="xs">
            <Button variant="default" size="xs" leftSection={<IconDownload size={14} />} onClick={() => downloadJson(result)}>
              Download JSON
            </Button>
            <Button variant="default" size="xs" leftSection={<IconRefresh size={14} />} onClick={onStart}>
              Re-run
            </Button>
          </Group>
        )}
      </Group>

      {status === 'idle' && <Idle validations={validations} onStart={onStart} />}
      {status === 'running' && <Running elapsed={elapsed} validations={validations} />}
      {status === 'error' && (
        <Alert color="red" icon={<IconAlertTriangle />} title="The investigation failed">
          <Text size="sm">{error?.message}</Text>
          <Button mt="sm" size="xs" color="red" variant="light" leftSection={<IconRefresh size={14} />} onClick={onStart}>
            Try again
          </Button>
        </Alert>
      )}
      {status === 'done' && result && <InvestigationResult result={result} />}
    </Card>
  );
}
