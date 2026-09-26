import { Accordion, Badge, Box, Code, Group, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconPlayerSkipForward, IconX } from '@tabler/icons-react';

// Presentation for the contract's status and severity values (CONTRACT.md §9). Any other value is shown as-is.
const STATUS_STYLE = {
  FAILED: { color: 'red', icon: IconX, order: 0 },
  WARNING: { color: 'yellow', icon: IconAlertTriangle, order: 1 },
  SKIPPED: { color: 'gray', icon: IconPlayerSkipForward, order: 2 },
  PASSED: { color: 'green', icon: IconCheck, order: 3 },
};
const SEVERITY_COLOR = { ERROR: 'red', WARNING: 'yellow', INFO: 'blue' };
/** "not_null.order_ref" -> "Not null · order ref"; keeps every part of the backend's name. */
export function checkLabel(name) {
  const parts = String(name).split('.').map((p) => p.replace(/_/g, ' '));
  const text = parts.join(' · ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const metricLabel = (key) => {
  const s = String(key).replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
};

const styleFor = (status) => STATUS_STYLE[status] ?? { color: 'gray', icon: IconAlertTriangle, order: 1.5 };

/** Metrics exactly as returned: scalars as numbers, value -> count maps as badges, anything else as JSON. */
function Metrics({ metrics }) {
  const entries = Object.entries(metrics ?? {});
  if (!entries.length) return null;
  return (
    <Group gap="lg" align="flex-start">
      {entries.map(([key, value]) => (
        <div key={key}>
          <Text size="xs" c="dimmed">{metricLabel(key)}</Text>
          {value && typeof value === 'object' && !Array.isArray(value) ? (
            <Group gap={4} mt={2}>
              {Object.entries(value).map(([k, v]) => (
                <Badge key={k} variant="outline" color="gray" tt="none">{k} × {String(v)}</Badge>
              ))}
            </Group>
          ) : (
            <Text size="sm" fw={600}>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</Text>
          )}
        </div>
      ))}
    </Group>
  );
}

/** Evidence lines are the backend's deterministic facts: shown verbatim, one per line, never rewritten. */
function Evidence({ lines }) {
  if (!lines?.length) return null;
  return (
    <div>
      <Text size="xs" c="dimmed" mb={4}>Evidence</Text>
      <Box component="ul" m={0} p={0} style={{ listStyle: 'none' }} aria-label="Evidence">
        {lines.map((line, i) => (
          <li key={i}>
            <Code block fz="xs" mb={4} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{line}</Code>
          </li>
        ))}
      </Box>
    </div>
  );
}

/**
 * Every validation result from the backend, in the backend's order within each status group
 * (failed, then warnings, skipped, passed). Failed and warning results start expanded.
 * @param {{results: import('../types').RunValidationResult[]}} props
 */
export default function RunValidationResults({ results }) {
  if (!results?.length) {
    return <Text size="sm" c="dimmed">The backend returned no validation results for this run.</Text>;
  }
  const sorted = results
    .map((r, i) => ({ r, i }))
    .sort((a, b) => styleFor(a.r.status).order - styleFor(b.r.status).order || a.i - b.i);
  const open = sorted.filter(({ r }) => r.status === 'FAILED' || r.status === 'WARNING').map(({ i }) => String(i));

  return (
    <Accordion variant="separated" radius="md" multiple defaultValue={open}>
      {sorted.map(({ r, i }) => {
        const s = styleFor(r.status);
        return (
          <Accordion.Item key={i} value={String(i)} data-testid="validation-result" data-status={r.status}>
            <Accordion.Control
              icon={<ThemeIcon color={s.color} variant="light" radius="xl" size={26}><s.icon size={16} /></ThemeIcon>}
            >
              <div style={{ minWidth: 0 }}>
                <Group gap={6} wrap="wrap">
                  <Text size="sm" fw={600}>{checkLabel(r.name)}</Text>
                  <Badge color={s.color} variant="light" size="sm">{r.status}</Badge>
                  {r.severity && <Badge color={SEVERITY_COLOR[r.severity] ?? 'gray'} variant="outline" size="sm">{r.severity}</Badge>}
                </Group>
                <Text size="xs" c="dimmed" ff="monospace" style={{ overflowWrap: 'anywhere' }}>{r.name}</Text>
                {r.summary && <Text size="sm" mt={2}>{r.summary}</Text>}
              </div>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap="md">
                <Metrics metrics={r.metrics} />
                <Evidence lines={r.evidence} />
                {!Object.keys(r.metrics ?? {}).length && !r.evidence?.length && (
                  <Text size="sm" c="dimmed">No metrics or evidence reported for this check.</Text>
                )}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        );
      })}
    </Accordion>
  );
}
