import { Alert, Badge, Button, Card, Code, Container, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import {
  IconAlertTriangle, IconArrowLeft, IconCircleCheck, IconCircleX, IconClock, IconFileUpload, IconInfoCircle, IconLoader2,
} from '@tabler/icons-react';
import RunValidationResults from '../components/RunValidationResults';
import { formatDateTime } from '../utils';

/**
 * How each backend run status (CONTRACT.md §13) is presented. The wording follows the contract's meaning of
 * the status; nothing is inferred from counts. An unknown status is shown as returned.
 */
const STATUS_VIEW = {
  CREATED: {
    color: 'indigo', icon: IconCircleCheck, title: 'Run created',
    subtitle: 'The backend accepted the file and created a run.',
    note: { title: 'Ready for validation', text: 'Validation against the target schema is the next stage.' },
  },
  VALIDATING: {
    color: 'blue', icon: IconLoader2, title: 'Validating',
    subtitle: 'The backend is checking the file against the target table.',
  },
  FAILED_VALIDATION: {
    color: 'red', icon: IconCircleX, title: 'Validation failed',
    subtitle: 'The file does not satisfy the target table’s contract. Nothing was written to the table.',
  },
  LOADING: {
    color: 'teal', icon: IconClock, title: 'Validation passed',
    subtitle: 'The required checks passed. Loading into the target table has not completed.',
  },
  SUCCEEDED: {
    color: 'green', icon: IconCircleCheck, title: 'Run succeeded',
    subtitle: 'The backend reports the run as succeeded.',
  },
  LOAD_FAILED: {
    color: 'red', icon: IconAlertTriangle, title: 'Load failed',
    subtitle: 'The database load failed and was rolled back.',
  },
};
const statusLabel = (status) => String(status).replace(/_/g, ' ');
const viewFor = (status) => STATUS_VIEW[status] ?? {
  color: 'gray', icon: IconInfoCircle, title: `Run ${statusLabel(status).toLowerCase()}`,
  subtitle: `The backend reports the status ${status}.`,
};

function Fact({ label, children }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
      <Text size="sm" fw={500} style={{ overflowWrap: 'anywhere' }}>{children}</Text>
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <Card padding="sm" radius="md" bg="var(--mantine-color-body)" data-testid={`stat-${label.toLowerCase()}`}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
      <Text fz={26} fw={700} lh={1.2} c={value ? color : undefined}>{value ?? '–'}</Text>
    </Card>
  );
}

/**
 * Compact validation summary. Checks, passed and failed come from the backend's `summary`; the contract's
 * summary has no warning/skipped counts, so those are counted from `validation_results` and only shown
 * when present.
 */
function ValidationSummary({ run }) {
  const s = run.summary ?? {};
  const count = (status) => (run.validation_results ?? []).filter((r) => r.status === status).length;
  const warnings = count('WARNING');
  const skipped = count('SKIPPED');
  return (
    <SimpleGrid cols={{ base: 2, xs: 3, sm: 2 + [warnings, skipped].filter(Boolean).length + 1 }} spacing="sm">
      <Stat label="Checks" value={s.checks_total} />
      <Stat label="Passed" value={s.checks_passed} color="green" />
      <Stat label="Failed" value={s.checks_failed} color="red" />
      {warnings > 0 && <Stat label="Warnings" value={warnings} color="yellow" />}
      {skipped > 0 && <Stat label="Skipped" value={skipped} color="gray" />}
    </SimpleGrid>
  );
}

/** The run returned by POST /api/runs (or GET /api/runs/{run_id}), rendered from its status and results. */
export default function RunResultPage({ run, target, onUploadAnother, onChooseTarget }) {
  const view = viewFor(run.status);
  const rows = run.summary?.rows_received;
  const hasResults = (run.validation_results?.length ?? 0) > 0;

  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <Group gap="sm" wrap="nowrap" align="flex-start">
          <ThemeIcon size={44} radius="xl" color={view.color} variant="light"><view.icon size={26} /></ThemeIcon>
          <div>
            <Title order={1} fz={{ base: 24, sm: 30 }}>{view.title}</Title>
            <Text c="dimmed">{view.subtitle}</Text>
          </div>
        </Group>

        <Card>
          <Group justify="space-between" align="flex-start" mb="md" gap="sm">
            <div>
              <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Run ID</Text>
              <Code fz="md" data-testid="run-id">{run.run_id}</Code>
            </div>
            <Badge size="lg" variant="light" color={view.color} data-testid="run-status">{statusLabel(run.status)}</Badge>
          </Group>
          <SimpleGrid cols={{ base: 1, xs: 2, sm: 4 }} spacing="md">
            <Fact label="Target">
              {target?.display_name ?? run.target_id}{' '}
              <Text span size="xs" c="dimmed" ff="monospace">({run.target_table})</Text>
            </Fact>
            <Fact label="File">{run.file_name}</Fact>
            <Fact label="Rows received">{typeof rows === 'number' ? rows.toLocaleString() : '–'}</Fact>
            <Fact label="Created">{run.created_at ? formatDateTime(run.created_at) : '–'}</Fact>
          </SimpleGrid>
        </Card>

        {view.note && (
          <Alert color={view.color} variant="light" icon={<IconInfoCircle />} title={view.note.title}>{view.note.text}</Alert>
        )}

        {(hasResults || run.status !== 'CREATED') && (
          <Card>
            <Title order={2} fz="lg" mb="sm">Validation</Title>
            <Stack gap="md">
              <ValidationSummary run={run} />
              <RunValidationResults results={run.validation_results} />
            </Stack>
          </Card>
        )}

        {/* Next steps. Later milestones add their actions here (e.g. investigate, fix and retry). */}
        <Group justify="space-between" data-testid="run-actions">
          <Button variant="default" leftSection={<IconArrowLeft size={16} />} onClick={onChooseTarget}>
            Choose another target
          </Button>
          <Button variant="light" leftSection={<IconFileUpload size={16} />} onClick={onUploadAnother}>
            Upload another file
          </Button>
        </Group>
      </Stack>
    </Container>
  );
}
