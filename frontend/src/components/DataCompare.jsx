import { useMemo, useState } from 'react';
import { Badge, Group, SegmentedControl, Stack, Switch, Table, Text } from '@mantine/core';
import { isBlank, isValidEmail } from '../utils';

const ISSUE_COLOR = { 'Missing in target': 'red', 'Null ID': 'red', Duplicate: 'orange', 'Invalid email': 'yellow' };

function annotate(source, target) {
  const key = (v) => (isBlank(v) ? null : String(v).trim());
  const targetIds = new Set(target.map((r) => key(r.customer_id)).filter(Boolean));
  const counts = {};
  target.forEach((r) => {
    const k = key(r.customer_id);
    if (k) counts[k] = (counts[k] || 0) + 1;
  });

  const src = source.map((r) => {
    const issues = [];
    if (!targetIds.has(key(r.customer_id))) issues.push('Missing in target');
    if (!isValidEmail(r.email)) issues.push('Invalid email');
    return { row: r, issues };
  });
  const tgt = target.map((r) => {
    const issues = [];
    const k = key(r.customer_id);
    if (!k) issues.push('Null ID');
    else if (counts[k] > 1) issues.push('Duplicate');
    if (!isValidEmail(r.email)) issues.push('Invalid email');
    return { row: r, issues };
  });
  return { source: src, target: tgt };
}

export default function DataCompare({ source, target }) {
  const [side, setSide] = useState('target');
  const [onlyIssues, setOnlyIssues] = useState(false);
  const annotated = useMemo(() => annotate(source, target), [source, target]);

  const rows = annotated[side];
  const shown = onlyIssues ? rows.filter((r) => r.issues.length) : rows;
  const cols = Object.keys((side === 'target' ? target : source)[0] ?? {});
  const issueCount = rows.filter((r) => r.issues.length).length;

  return (
    <Stack gap="sm">
      <Group justify="space-between" gap="sm">
        <SegmentedControl
          value={side}
          onChange={setSide}
          data={[
            { value: 'source', label: `Source (${source.length})` },
            { value: 'target', label: `Target (${target.length})` },
          ]}
        />
        <Switch
          label={`Only rows with issues (${issueCount})`}
          checked={onlyIssues}
          onChange={(e) => setOnlyIssues(e.currentTarget.checked)}
        />
      </Group>
      <Table.ScrollContainer minWidth={760} maxHeight={480}>
        <Table stickyHeader highlightOnHover verticalSpacing={6} fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={40}>#</Table.Th>
              {cols.map((c) => <Table.Th key={c}>{c}</Table.Th>)}
              <Table.Th>Issues</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {shown.map(({ row, issues }, i) => {
              const severe = issues.some((x) => ISSUE_COLOR[x] !== 'yellow');
              return (
                <Table.Tr key={i} className={issues.length ? (severe ? 'row-issue' : 'row-warn') : undefined}>
                  <Table.Td c="dimmed">{rows.indexOf(shown[i]) + 1}</Table.Td>
                  {cols.map((c) => (
                    <Table.Td key={c}>
                      {isBlank(row[c]) ? <Text span c="red" size="sm" fs="italic">null</Text> : row[c]}
                    </Table.Td>
                  ))}
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      {issues.map((x) => <Badge key={x} size="sm" variant="light" color={ISSUE_COLOR[x]}>{x}</Badge>)}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {shown.length === 0 && <Text size="sm" c="dimmed" ta="center" py="md">No rows with issues.</Text>}
    </Stack>
  );
}
