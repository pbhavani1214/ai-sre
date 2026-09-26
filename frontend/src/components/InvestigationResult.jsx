import { Alert, Badge, Group, List, Paper, SimpleGrid, Spoiler, Stack, Tabs, Text, ThemeIcon, Timeline } from '@mantine/core';
import {
  IconAlertTriangle, IconBulb, IconFlask, IconListSearch, IconRoute, IconSearch, IconTarget,
} from '@tabler/icons-react';
import HypothesisList from './HypothesisList';
import CodeBlock from './CodeBlock';
import CitedList from './CitedList';
import { humanize } from '../utils';

export function downloadJson(result, fileName = 'investigation.json') {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: fileName });
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * A run-scoped AI investigation result (POST /api/runs/{run_id}/investigate). With `reasoningOpen`, the root-cause
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
