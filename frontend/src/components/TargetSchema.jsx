import { Badge, Code, Group, Stack, Table, Text, Title } from '@mantine/core';

/** "PRIMARY_KEY" -> "Primary key" */
export const constraintLabel = (type) => {
  const s = String(type).toLowerCase().replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
};

/** Constraint types that apply to a column, beyond what the column flags already show. */
function extraConstraintTypes(column, constraints) {
  const shown = new Set(['PRIMARY_KEY', 'UNIQUE', 'NOT_NULL']);
  return [...new Set(
    constraints.filter((c) => c.columns?.includes(column.name) && !shown.has(c.type)).map((c) => c.type),
  )];
}

function ColumnFlags({ column, constraints }) {
  return (
    <Group gap={4} wrap="wrap">
      {column.primary_key && <Badge size="sm" variant="light" color="indigo">Primary key</Badge>}
      {column.unique && <Badge size="sm" variant="light" color="grape">Unique</Badge>}
      {!column.nullable && <Badge size="sm" variant="light" color="orange">Required</Badge>}
      {extraConstraintTypes(column, constraints).map((t) => (
        <Badge key={t} size="sm" variant="light" color="teal">{constraintLabel(t)}</Badge>
      ))}
    </Group>
  );
}

/** Renders a TargetDetail's columns and constraints exactly as the API returns them. */
export default function TargetSchema({ detail }) {
  const constraints = detail.constraints ?? [];
  return (
    <Stack gap="lg">
      <div>
        <Title order={4} fz="md" mb="xs">Columns</Title>
        <Table.ScrollContainer minWidth={280}>
          <Table verticalSpacing="xs" striped aria-label="Target columns">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Column</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Constraints</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {detail.columns.map((column) => (
                <Table.Tr key={column.name}>
                  <Table.Td><Code>{column.name}</Code></Table.Td>
                  <Table.Td><Text size="sm" ff="monospace">{column.data_type}</Text></Table.Td>
                  <Table.Td>
                    <ColumnFlags column={column} constraints={constraints} />
                    {column.nullable && !column.primary_key && !column.unique && !extraConstraintTypes(column, constraints).length && (
                      <Text size="xs" c="dimmed">Optional</Text>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </div>

      <div>
        <Title order={4} fz="md" mb="xs">Constraints</Title>
        {constraints.length === 0 ? (
          <Text size="sm" c="dimmed">This table declares no constraints.</Text>
        ) : (
          <Stack gap="xs">
            {constraints.map((c, i) => (
              <Group key={`${c.type}-${i}`} gap="sm" wrap="nowrap" align="flex-start">
                <Badge variant="outline" w={110} style={{ flexShrink: 0 }}>{constraintLabel(c.type)}</Badge>
                <div>
                  <Group gap={4}>
                    {c.columns?.map((col) => <Code key={col}>{col}</Code>)}
                  </Group>
                  {c.description && <Text size="sm" mt={2}>{c.description}</Text>}
                  {c.allowed_values?.length > 0 && (
                    <Group gap={4} mt={4}>
                      <Text size="xs" c="dimmed">Allowed:</Text>
                      {c.allowed_values.map((v) => <Badge key={v} size="sm" variant="default" tt="none">{v}</Badge>)}
                    </Group>
                  )}
                </div>
              </Group>
            ))}
          </Stack>
        )}
      </div>
    </Stack>
  );
}
