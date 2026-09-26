import { useRef, useState } from 'react';
import { Alert, Badge, Box, Button, Code, Group, Paper, Stack, Table, Text, Tooltip } from '@mantine/core';
import { IconAlertTriangle, IconDownload, IconRefresh } from '@tabler/icons-react';
import { getSuggestedCsv, retryRun } from '../services/api';
import { describeUploadError } from '../services/errors';

const ACTION = {
  REPLACE: { label: 'Replace', color: 'blue' },
  DELETE_ROW: { label: 'Delete row', color: 'orange' },
  NEEDS_DECISION: { label: 'Decide', color: 'gray' },
};
const CONFIDENCE = { HIGH: 'green', MEDIUM: 'yellow', LOW: 'gray' };

export const suggestedFileName = (fileName) => `${(fileName || 'upload.csv').replace(/\.csv$/i, '') || 'upload'}_suggested.csv`;

function saveText(text, fileName) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: fileName });
  a.click();
  URL.revokeObjectURL(url);
}

function Badges({ fix }) {
  return (
    <Group gap={4} wrap="nowrap">
      <Badge size="sm" variant="light" color={ACTION[fix.action]?.color ?? 'gray'} style={{ flexShrink: 0 }}>
        {ACTION[fix.action]?.label ?? fix.action}
      </Badge>
      <Tooltip label={`${fix.confidence.toLowerCase()} confidence`} withArrow>
        <Badge size="sm" variant="outline" color={CONFIDENCE[fix.confidence] ?? 'gray'} style={{ flexShrink: 0 }}>
          {fix.confidence.toLowerCase()}
        </Badge>
      </Tooltip>
    </Group>
  );
}

function Suggested({ fix }) {
  if (fix.action !== 'REPLACE') return <Value value={null} />;
  return (
    <Group gap={4} wrap="nowrap">
      <Value value={fix.suggested_value} />
      {!fix.satisfies_constraints && (
        <Tooltip label="This value does not pass the column's rules; review it" withArrow>
          <IconAlertTriangle size={14} color="var(--mantine-color-yellow-7)" aria-label="Fails the column's rules" />
        </Tooltip>
      )}
    </Group>
  );
}

function Value({ value }) {
  if (value === null || value === undefined) return <Text span size="sm" c="dimmed">–</Text>;
  if (value === '') return <Text span size="sm" c="dimmed" fs="italic">empty</Text>;
  return <Code style={{ overflowWrap: 'anywhere', whiteSpace: 'normal' }}>{value}</Code>;
}

/**
 * The AI's row-level fixes for the uploaded file (checked by the backend against the file), with a suggested corrected
 * CSV to download or retry with. The suggested file only applies REPLACE and DELETE_ROW; the backend validates it again.
 */
export default function SuggestedFixes({ runId, fileName, fixes, onRetried }) {
  const [busy, setBusy] = useState(null); // 'download' | 'retry'
  const [error, setError] = useState(null);
  const inFlight = useRef(false);
  const applicable = fixes.filter((f) => f.action !== 'NEEDS_DECISION').length;
  const undecided = fixes.length - applicable;

  const run = async (kind) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(kind);
    setError(null);
    try {
      const text = await getSuggestedCsv(runId);
      const name = suggestedFileName(fileName);
      if (kind === 'download') saveText(text, name);
      else onRetried(await retryRun(runId, new File([text], name, { type: 'text/csv' })));
    } catch (e) {
      setError(kind === 'retry' ? describeUploadError(e) : { title: 'Could not get the suggested file', message: e.message });
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  };

  return (
    <Stack gap="sm" data-testid="row-fixes">
      <Box visibleFrom="sm">
        <Table verticalSpacing="xs" striped aria-label="Suggested fixes">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Row</Table.Th>
              <Table.Th>Column</Table.Th>
              <Table.Th>Now</Table.Th>
              <Table.Th>Suggested</Table.Th>
              <Table.Th>Action</Table.Th>
              <Table.Th>Why</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {fixes.map((f, i) => (
              <Table.Tr key={i}>
                <Table.Td>{f.row}</Table.Td>
                <Table.Td><Text size="sm" ff="monospace">{f.column ?? '(whole row)'}</Text></Table.Td>
                <Table.Td><Value value={f.action === 'DELETE_ROW' ? null : f.current_value} /></Table.Td>
                <Table.Td><Suggested fix={f} /></Table.Td>
                <Table.Td miw={170}><Badges fix={f} /></Table.Td>
                <Table.Td><Text size="sm">{f.reason}</Text></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Box>
      <Stack gap="xs" hiddenFrom="sm" aria-label="Suggested fixes (list)">
        {fixes.map((f, i) => (
          <Paper key={i} withBorder p="sm" radius="md">
            <Group justify="space-between" gap="xs" mb={4}>
              <Text size="sm" fw={600}>Row {f.row} · <Text span ff="monospace" size="sm">{f.column ?? 'whole row'}</Text></Text>
              <Badges fix={f} />
            </Group>
            {f.action !== 'DELETE_ROW' && (
              <Group gap={6} mb={4} wrap="wrap">
                <Value value={f.current_value} />
                {f.action === 'REPLACE' && <><Text span size="sm" c="dimmed">→</Text><Suggested fix={f} /></>}
              </Group>
            )}
            <Text size="sm">{f.reason}</Text>
          </Paper>
        ))}
      </Stack>

      {undecided > 0 && (
        <Text size="sm" c="dimmed">
          {undecided} value{undecided === 1 ? '' : 's'} need{undecided === 1 ? 's' : ''} your decision. The suggested file
          leaves {undecided === 1 ? 'it' : 'them'} as uploaded, so it will still fail until you correct {undecided === 1 ? 'it' : 'them'}.
        </Text>
      )}

      {error && (
        <Alert color="red" variant="light" icon={<IconAlertTriangle />} title={error.title} role="alert">
          {error.message && <Text size="sm">{error.message}</Text>}
        </Alert>
      )}

      {applicable > 0 && (
        <Group gap="xs">
          <Button variant="default" size="xs" leftSection={<IconDownload size={14} />} loading={busy === 'download'}
            disabled={busy !== null} onClick={() => run('download')}>
            Download suggested CSV
          </Button>
          {onRetried && (
            <Button size="xs" color="teal" leftSection={<IconRefresh size={14} />} loading={busy === 'retry'}
              disabled={busy !== null} onClick={() => run('retry')}>
              Retry with suggested CSV
            </Button>
          )}
        </Group>
      )}
      <Text size="xs" c="dimmed">
        Suggested by the AI and checked against your file. Nothing is changed until you retry; the retry is validated again.
      </Text>
    </Stack>
  );
}
