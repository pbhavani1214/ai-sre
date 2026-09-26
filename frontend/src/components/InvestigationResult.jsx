import {
  Alert, Badge, Button, Group, List, Paper, SimpleGrid, Spoiler, Stack, Tabs, Text, ThemeIcon, Timeline,
} from '@mantine/core';
import {
  IconAlertTriangle, IconBulb, IconDownload, IconFlask, IconListSearch, IconPencil, IconRoute, IconSearch,
  IconShieldCheck, IconTarget,
} from '@tabler/icons-react';
import HypothesisList from './HypothesisList';
import CodeBlock from './CodeBlock';
import CitedList from './CitedList';
import SuggestedFixes from './SuggestedFixes';
import { humanize } from '../utils';

const CATEGORY_COLOR = {
  SOURCE_FORMAT: 'violet', DATA_ENTRY: 'orange', DUPLICATE_RECORD: 'red', NEW_VALUE: 'cyan', EXISTING_DATA: 'grape',
};
const SCHEMA_TEST = /Data check for table `([^`]+)`/;

function downloadText(text, fileName, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: fileName });
  a.click();
  URL.revokeObjectURL(url);
}

function Section({ icon: Icon, color, title, children, badge, testId }) {
  return (
    <Paper withBorder p="md" radius="md" style={{ borderLeft: `4px solid var(--mantine-color-${color}-6)`, minWidth: 0 }}
      data-testid={testId}>
      <Group gap="xs" mb="xs">
        <ThemeIcon color={color} variant="light"><Icon size={16} /></ThemeIcon>
        <Text fw={600}>{title}</Text>
        {badge}
      </Group>
      {children}
    </Paper>
  );
}

function CauseGroups({ groups }) {
  return (
    <Stack gap="xs" data-testid="cause-groups">
      <Text size="xs" fw={600} tt="uppercase" c="dimmed">Likely causes</Text>
      {groups.map((g, i) => (
        <Paper key={i} withBorder p="sm" radius="md">
          <Group gap="xs" mb={4}>
            <Text size="sm" fw={600}>{g.title}</Text>
            <Badge size="xs" variant="light" color={CATEGORY_COLOR[g.category] ?? 'gray'}>{humanize(g.category.toLowerCase())}</Badge>
          </Group>
          <Text size="sm">{g.explanation}</Text>
          {(g.rows?.length > 0 || g.checks?.length > 0) && (
            <Group gap={6} mt={6}>
              {g.rows?.length > 0 && <Badge size="xs" variant="outline" color="gray">rows {g.rows.join(', ')}</Badge>}
              {g.checks?.map((c) => <Badge key={c} size="xs" variant="outline" color="gray">{humanize(c)}</Badge>)}
            </Group>
          )}
        </Paper>
      ))}
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
 * A run-scoped AI investigation result (POST /api/runs/{run_id}/investigate). With `reasoningOpen`, the root-cause
 * reasoning and evidence are shown directly instead of behind "Why?". Results with the v2.2 fields (cause groups, row
 * fixes, prevention) lead with the root cause, then "Fix this file", then "Prevent it next time".
 */
export function InvestigationResult({ result: raw, reasoningOpen = false, runId, fileName, onRetried }) {
  const result = {
    ...raw,
    hypotheses: raw.hypotheses ?? [], observed_facts: raw.observed_facts ?? [], root_cause_evidence: raw.root_cause_evidence ?? [],
    investigation_trace: raw.investigation_trace ?? [], evidence_warnings: raw.evidence_warnings ?? [],
    cause_groups: raw.cause_groups ?? [], row_fixes: raw.row_fixes ?? [], prevention: raw.prevention ?? [],
  };
  const supported = result.hypotheses.filter((h) => h.status === 'SUPPORTED').length;
  const identified = result.root_cause_status === 'IDENTIFIED';
  const guided = result.cause_groups.length > 0 || result.row_fixes.length > 0 || result.prevention.length > 0;
  const schemaTest = SCHEMA_TEST.exec(result.regression_test ?? '');

  const reasoning = reasoningOpen ? (
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
  );
  const rootCause = (
    <Section icon={IconTarget} color="red" title="Root cause" testId="root-cause"
      badge={<Badge size="sm" variant="light" color={identified ? 'red' : 'yellow'}>{identified ? 'Identified' : 'Inconclusive'}</Badge>}>
      <Text size="sm" style={{ whiteSpace: 'pre-line' }}>{result.root_cause}</Text>
      {guided && result.cause_groups.length > 0 && <Stack mt="md"><CauseGroups groups={result.cause_groups} /></Stack>}
      {guided ? (
        <Spoiler maxHeight={0} showLabel="Show reasoning and evidence" hideLabel="Hide reasoning" mt="sm">{reasoning}</Spoiler>
      ) : reasoning}
    </Section>
  );
  const recommendedFix = (
    <Section icon={IconBulb} color="green" title="Recommended fix">
      <Text size="sm" style={{ whiteSpace: 'pre-line' }}>{result.recommended_fix}</Text>
    </Section>
  );

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

      {guided ? (
        <>
          {rootCause}
          {result.row_fixes.length > 0 ? (
            <Section icon={IconPencil} color="blue" title="Fix this file" testId="fix-this-file"
              badge={<Badge size="sm" variant="light">{result.row_fixes.length}</Badge>}>
              <Text size="sm" mb="sm" style={{ whiteSpace: 'pre-line' }}>{result.recommended_fix}</Text>
              <SuggestedFixes runId={runId} fileName={fileName} fixes={result.row_fixes} onRetried={onRetried} />
            </Section>
          ) : recommendedFix}
          {result.prevention.length > 0 && (
            <Section icon={IconShieldCheck} color="green" title="Prevent it next time" testId="prevention">
              <List size="sm" spacing={4}>
                {result.prevention.map((p, i) => <List.Item key={i}>{p}</List.Item>)}
              </List>
            </Section>
          )}
        </>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {rootCause}
          {recommendedFix}
        </SimpleGrid>
      )}

      <Tabs defaultValue="hypotheses" keepMounted={false}>
        <Tabs.List className="scroll-tabs">
          <Tabs.Tab value="hypotheses" leftSection={<IconSearch size={16} />}>
            Hypotheses <Badge size="xs" variant="light" ml={4}>{supported}/{result.hypotheses.length}</Badge>
          </Tabs.Tab>
          <Tabs.Tab value="test" leftSection={<IconFlask size={16} />}>Regression test</Tabs.Tab>
          <Tabs.Tab value="trace" leftSection={<IconRoute size={16} />}>Trace</Tabs.Tab>
          <Tabs.Tab value="facts" leftSection={<IconListSearch size={16} />}>
            Evidence reviewed <Badge size="xs" variant="light" color="gray" ml={4}>{result.observed_facts.length}</Badge>
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="hypotheses" pt="md">
          <HypothesisList hypotheses={result.hypotheses} />
        </Tabs.Panel>

        <Tabs.Panel value="test" pt="md">
          <Stack gap="sm">
            {schemaTest ? (
              <Group justify="space-between" gap="xs">
                <Text size="sm" c="dimmed" style={{ flex: 1, minWidth: 220 }}>
                  Generated from the schema of <Text span ff="monospace">{schemaTest[1]}</Text>, not by the AI. Run it
                  with pytest; set <Text span ff="monospace">CSV_PATH</Text> to check a file before you upload it.
                </Text>
                <Button variant="default" size="xs" leftSection={<IconDownload size={14} />}
                  onClick={() => downloadText(result.regression_test, `test_${schemaTest[1].toLowerCase().replace(/[^a-z0-9_]+/g, '_')}_data.py`, 'text/x-python')}>
                  Download test file
                </Button>
              </Group>
            ) : null}
            <CodeBlock code={result.regression_test} />
            <Text size="xs" c="dimmed">
              {schemaTest ? 'This system never executes it.' : 'Generated by the AI for review. This system never executes generated code.'}
            </Text>
          </Stack>
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

        <Tabs.Panel value="facts" pt="md">
          <Stack gap="xs">
            <Text size="xs" c="dimmed">The validation evidence the AI based its conclusions on.</Text>
            <CitedList items={result.observed_facts} empty="No facts reported." />
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
