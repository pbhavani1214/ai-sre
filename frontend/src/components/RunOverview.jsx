import { Alert, Badge, Button, Card, Group, SimpleGrid, Spoiler, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconCircleCheck, IconSparkles } from '@tabler/icons-react';
import { durationBetween, formatDateTime } from '../utils';

function Stat({ label, value, hint, color }) {
  return (
    <Card padding="md" radius="md" bg="var(--mantine-color-body)">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
      <Text fz={28} fw={700} c={color} lh={1.3}>{value}</Text>
      <Text size="xs" c="dimmed">{hint}</Text>
    </Card>
  );
}

export default function RunOverview({ run, description, validations, investigationStatus, onInvestigate }) {
  const failed = validations.filter((v) => !v.passed);
  const byCheck = Object.fromEntries(validations.map((v) => [v.check, v]));
  const counts = byCheck.record_count_comparison?.details ?? {};
  const missing = byCheck.missing_target_records?.details.missing_count ?? 0;
  const extra = byCheck.duplicate_customer_id_check?.details.extra_rows ?? 0;
  const running = investigationStatus === 'running';

  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" gap="md">
          <div>
            <Group gap="xs" mb={4}>
              <Title order={2} fz={{ base: 20, sm: 24 }}>{run.pipeline}</Title>
              <Badge color="green" variant="light" leftSection={<IconCircleCheck size={12} />}>
                Reported {run.status}
              </Badge>
            </Group>
            <Text size="sm" c="dimmed">
              Run <Text span ff="monospace" size="sm">{run.run_id}</Text> · {formatDateTime(run.started_at)} ·{' '}
              {durationBetween(run.started_at, run.finished_at)}
            </Text>
          </div>
          <Button
            size="md"
            leftSection={<IconSparkles size={18} />}
            onClick={onInvestigate}
            loading={running}
            variant="gradient"
            gradient={{ from: 'indigo', to: 'cyan' }}
          >
            {investigationStatus === 'done' ? 'Investigate again' : 'Investigate with AI'}
          </Button>
        </Group>

        <Spoiler maxHeight={44} showLabel="Show more" hideLabel="Show less">
          <Text size="sm">{description}</Text>
        </Spoiler>

        {failed.length > 0 ? (
          <Alert color="red" variant="light" icon={<IconAlertTriangle />} title="The run says SUCCESS, but the data disagrees">
            {failed.length} of {validations.length} data checks failed. Review the evidence below or let the AI
            investigate the root cause.
          </Alert>
        ) : (
          <Alert color="green" variant="light" icon={<IconCircleCheck />} title="All data checks passed" />
        )}

        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
          <Stat label="Source rows" value={counts.source_count ?? '–'} hint="Rows extracted" />
          <Stat
            label="Target rows"
            value={counts.target_count ?? '–'}
            hint={counts.difference ? `${counts.difference > 0 ? '+' : ''}${counts.difference} vs source` : 'Matches source'}
            color={counts.difference ? 'orange' : undefined}
          />
          <Stat label="Missing" value={missing} hint="Source customers not in target" color={missing ? 'red' : undefined} />
          <Stat label="Duplicates" value={extra} hint="Extra rows in target" color={extra ? 'red' : undefined} />
        </SimpleGrid>
      </Stack>
    </Card>
  );
}
