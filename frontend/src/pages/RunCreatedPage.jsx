import { Alert, Badge, Button, Card, Code, Container, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconArrowLeft, IconCircleCheck, IconClock, IconFileUpload, IconInfoCircle } from '@tabler/icons-react';
import { formatDateTime } from '../utils';

function Fact({ label, children }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
      <Text size="sm" fw={500} style={{ overflowWrap: 'anywhere' }}>{children}</Text>
    </div>
  );
}

/** Humanized status label; any value the backend sends is shown, never reinterpreted. */
const statusLabel = (status) => String(status).replace(/_/g, ' ');

/**
 * The run returned by POST /api/runs. This milestone only confirms the run exists: no validation, load or
 * AI results are shown or implied.
 */
export default function RunCreatedPage({ run, target, onUploadAnother, onChooseTarget }) {
  const created = run.status === 'CREATED';
  const rows = run.summary?.rows_received;

  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <Group gap="sm" wrap="nowrap">
          <ThemeIcon size={44} radius="xl" color="indigo" variant="light"><IconCircleCheck size={26} /></ThemeIcon>
          <div>
            <Title order={1} fz={{ base: 24, sm: 30 }}>Run created</Title>
            <Text c="dimmed">The backend accepted the file and created a run.</Text>
          </div>
        </Group>

        <Card>
          <Group justify="space-between" align="flex-start" mb="md" gap="sm">
            <div>
              <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Run ID</Text>
              <Code fz="md" data-testid="run-id">{run.run_id}</Code>
            </div>
            <Badge size="lg" variant="light" color={created ? 'indigo' : 'gray'} leftSection={<IconClock size={14} />}
              data-testid="run-status">
              {statusLabel(run.status)}
            </Badge>
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

        <Alert color="indigo" variant="light" icon={<IconInfoCircle />} title={created ? 'Ready for validation' : `Status: ${statusLabel(run.status)}`}>
          {created
            ? 'Validation against the target schema is the next stage. Its results will appear here once that step is available.'
            : 'Detailed results for this run will be shown here in a later step.'}
        </Alert>

        <Group justify="space-between">
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
