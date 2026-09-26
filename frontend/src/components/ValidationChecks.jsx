import { Accordion, Badge, Group, List, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconCheck, IconX } from '@tabler/icons-react';
import { humanize, isFailed } from '../utils';

const SEVERITY_COLOR = { HIGH: 'red', MEDIUM: 'orange', LOW: 'yellow' };
const SEVERITY_ORDER = { HIGH: 0, MEDIUM: 1, LOW: 2 };

/** Renders CheckResult.metrics generically: scalars as numbers, value -> count maps as badges. */
function Metrics({ metrics }) {
  const scalars = Object.entries(metrics).filter(([, v]) => typeof v !== 'object' || v === null);
  const maps = Object.entries(metrics).filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v));
  return (
    <Stack gap="sm">
      {scalars.length > 0 && (
        <Group gap="lg">
          {scalars.map(([k, v]) => (
            <div key={k}>
              <Text size="xs" c="dimmed">{humanize(k)}</Text>
              <Text size="sm" fw={600}>{String(v)}</Text>
            </div>
          ))}
        </Group>
      )}
      {maps.map(([k, v]) => (
        <div key={k}>
          <Text size="xs" c="dimmed" mb={4}>{humanize(k)}</Text>
          <Group gap={6}>
            {Object.entries(v).map(([id, n]) => (
              <Badge key={id} variant="outline" color="red" tt="none">{id} × {n}</Badge>
            ))}
          </Group>
        </div>
      ))}
    </Stack>
  );
}

export default function ValidationChecks({ validations }) {
  const sorted = [...validations].sort(
    (a, b) => Number(isFailed(b)) - Number(isFailed(a)) || SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );
  return (
    <Accordion variant="separated" radius="md" multiple>
      {sorted.map((v) => {
        const failed = isFailed(v);
        return (
          <Accordion.Item key={v.name} value={v.name}>
            <Accordion.Control
              icon={
                <ThemeIcon color={failed ? 'red' : 'green'} variant="light" radius="xl" size={26}>
                  {failed ? <IconX size={16} /> : <IconCheck size={16} />}
                </ThemeIcon>
              }
            >
              <Group justify="space-between" wrap="nowrap" gap="sm">
                <div>
                  <Text size="sm" fw={600}>{humanize(v.name)}</Text>
                  <Text size="xs" c="dimmed">{v.summary}</Text>
                </div>
                <Group gap={6} wrap="nowrap" visibleFrom="xs" style={{ flexShrink: 0 }}>
                  {failed && (
                    <Badge color={SEVERITY_COLOR[v.severity] ?? 'gray'} variant="outline">{v.severity}</Badge>
                  )}
                  <Badge color={failed ? 'red' : 'green'} variant="light">{failed ? 'Failed' : 'Passed'}</Badge>
                </Group>
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap="md">
                <Metrics metrics={v.metrics} />
                {v.evidence.length > 0 && (
                  <div>
                    <Text size="xs" c="dimmed" mb={4}>Evidence</Text>
                    <List size="sm" spacing={4}>
                      {v.evidence.map((e, i) => <List.Item key={i}>{e}</List.Item>)}
                    </List>
                  </div>
                )}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        );
      })}
    </Accordion>
  );
}
