import { Accordion, Badge, Group, Stack, Table, Text, ThemeIcon } from '@mantine/core';
import { IconCheck, IconX } from '@tabler/icons-react';
import { humanize } from '../utils';

function RowsTable({ rows }) {
  if (!rows.length) return null;
  const cols = Object.keys(rows[0]);
  return (
    <Table.ScrollContainer minWidth={500}>
      <Table withTableBorder fz="xs" verticalSpacing={4}>
        <Table.Thead>
          <Table.Tr>{cols.map((c) => <Table.Th key={c}>{c}</Table.Th>)}</Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r, i) => (
            <Table.Tr key={i}>
              {cols.map((c) => (
                <Table.Td key={c}>{r[c] ?? <Text span c="red" size="xs" fs="italic">null</Text>}</Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

/** Renders a ValidationResult.details object generically: scalars, id->count maps and row lists. */
function Details({ details }) {
  const scalars = Object.entries(details).filter(([, v]) => typeof v !== 'object' || v === null);
  const maps = Object.entries(details).filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v));
  const lists = Object.entries(details).filter(([, v]) => Array.isArray(v));
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
      {lists.map(([k, v]) => (
        <div key={k}>
          <Text size="xs" c="dimmed" mb={4}>{humanize(k)}</Text>
          <RowsTable rows={v} />
        </div>
      ))}
    </Stack>
  );
}

export default function ValidationChecks({ validations }) {
  const sorted = [...validations].sort((a, b) => Number(a.passed) - Number(b.passed));
  return (
    <Accordion variant="separated" radius="md" multiple>
      {sorted.map((v) => (
        <Accordion.Item key={v.check} value={v.check}>
          <Accordion.Control
            icon={
              <ThemeIcon color={v.passed ? 'green' : 'red'} variant="light" radius="xl" size={26}>
                {v.passed ? <IconCheck size={16} /> : <IconX size={16} />}
              </ThemeIcon>
            }
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <div>
                <Text size="sm" fw={600}>{humanize(v.check)}</Text>
                <Text size="xs" c="dimmed">{v.summary}</Text>
              </div>
              <Badge color={v.passed ? 'green' : 'red'} variant="light" visibleFrom="xs" style={{ flexShrink: 0 }}>
                {v.passed ? 'Passed' : 'Failed'}
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Details details={v.details} />
          </Accordion.Panel>
        </Accordion.Item>
      ))}
    </Accordion>
  );
}
