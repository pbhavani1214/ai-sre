import { Badge, Code, Grid, Group, Text, Timeline } from '@mantine/core';
import { IconAlertTriangle, IconCheck } from '@tabler/icons-react';
import { humanize } from '../utils';

function rowDelta(step) {
  const out = step.rows_out ?? step.rows_written;
  return out === undefined ? 0 : out - step.rows_in;
}

export default function PipelineSteps({ run }) {
  const { config, steps } = run;
  return (
    <Grid gutter="xl">
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Timeline bulletSize={26} lineWidth={2} active={steps.length}>
          {steps.map((step) => {
            const delta = rowDelta(step);
            const flagged = delta !== 0 || step.warnings?.length;
            return (
              <Timeline.Item
                key={step.name}
                color={flagged ? 'orange' : 'green'}
                bullet={flagged ? <IconAlertTriangle size={14} /> : <IconCheck size={14} />}
                title={
                  <Group gap="xs">
                    <Text fw={600} size="sm">{humanize(step.name)}</Text>
                    <Badge size="xs" variant="light" color="green">{step.status}</Badge>
                  </Group>
                }
              >
                <Text size="sm" c="dimmed">
                  {step.rows_in} rows in → {step.rows_out ?? step.rows_written} rows {step.rows_written !== undefined ? 'written' : 'out'}
                  {step.batches ? ` · ${step.batches} batches` : ''}
                </Text>
                {delta !== 0 && (
                  <Badge mt={6} color={delta < 0 ? 'red' : 'orange'} variant="light">
                    {delta > 0 ? `+${delta}` : delta} rows
                  </Badge>
                )}
                {step.warnings?.map((w) => (
                  <Text key={w} size="xs" c="orange" mt={6}>⚠ {w}</Text>
                ))}
              </Timeline.Item>
            );
          })}
        </Timeline>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Text size="xs" fw={600} tt="uppercase" c="dimmed" mb="xs">Configuration</Text>
        <Code block>{JSON.stringify(config, null, 2)}</Code>
      </Grid.Col>
    </Grid>
  );
}
