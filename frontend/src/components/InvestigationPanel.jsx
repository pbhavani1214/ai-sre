import { Alert, Badge, Button, Card, Code, Group, Loader, Paper, SimpleGrid, Stack, Table, Tabs, Text, ThemeIcon, Title } from '@mantine/core';
import {
  IconAlertTriangle, IconBulb, IconCheck, IconDownload, IconFlask, IconListSearch, IconRefresh,
  IconSearch, IconSparkles, IconTarget,
} from '@tabler/icons-react';
import HypothesisList from './HypothesisList';
import CodeBlock from './CodeBlock';

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
  const failed = validations.filter((v) => !v.passed).length;
  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        The AI reads only the evidence gathered from this run: validation results, source and target data, and
        the pipeline&apos;s config, steps and logs. It forms competing hypotheses, tests each against that evidence, and
        suggests a fix. Nothing is hardcoded and no generated code is executed.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        {[
          { icon: IconListSearch, t: '1. Evidence', d: `${validations.length} checks ready (${failed} failed), plus run logs` },
          { icon: IconSearch, t: '2. Hypotheses', d: 'Each is confirmed or rejected against the evidence' },
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

function downloadJson(result) {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: 'investigation.json' });
  a.click();
  URL.revokeObjectURL(url);
}

function Result({ result }) {
  const confirmed = result.hypotheses.filter((h) => h.status === 'confirmed').length;
  return (
    <Stack gap="lg">
      <Text>{result.summary}</Text>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Paper withBorder p="md" radius="md" style={{ borderLeft: '4px solid var(--mantine-color-red-6)' }}>
          <Group gap="xs" mb="xs">
            <ThemeIcon color="red" variant="light"><IconTarget size={16} /></ThemeIcon>
            <Text fw={600}>Root cause</Text>
          </Group>
          <Text size="sm" style={{ whiteSpace: 'pre-line' }}>{result.root_cause}</Text>
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
            Hypotheses <Badge size="xs" variant="light" ml={4}>{confirmed}/{result.hypotheses.length}</Badge>
          </Tabs.Tab>
          <Tabs.Tab value="evidence" leftSection={<IconListSearch size={16} />}>
            Evidence <Badge size="xs" variant="light" color="gray" ml={4}>{result.evidence.length}</Badge>
          </Tabs.Tab>
          <Tabs.Tab value="test" leftSection={<IconFlask size={16} />}>Regression test</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="hypotheses" pt="md">
          <HypothesisList hypotheses={result.hypotheses} />
        </Tabs.Panel>

        <Tabs.Panel value="evidence" pt="md">
          <Table.ScrollContainer minWidth={500}>
            <Table verticalSpacing="sm" striped highlightOnHover>
              <Table.Thead>
                <Table.Tr><Table.Th w={240}>Source</Table.Th><Table.Th>Observation</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {result.evidence.map((e, i) => (
                  <Table.Tr key={i}>
                    <Table.Td><Code>{e.source}</Code></Table.Td>
                    <Table.Td><Text size="sm">{e.observation}</Text></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Tabs.Panel>

        <Tabs.Panel value="test" pt="md">
          <Stack gap="sm">
            <div>
              <Text fw={600} ff="monospace" size="sm">{result.regression_test.name}</Text>
              <Text size="sm" c="dimmed">{result.regression_test.description}</Text>
            </div>
            <CodeBlock code={result.regression_test.code} />
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
      {status === 'done' && result && <Result result={result} />}
    </Card>
  );
}
