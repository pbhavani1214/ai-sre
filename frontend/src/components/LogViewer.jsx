import { useState } from 'react';
import { Badge, Group, Paper, SegmentedControl, Stack, Text } from '@mantine/core';

const LEVEL_COLOR = { INFO: 'blue', WARN: 'yellow', WARNING: 'yellow', ERROR: 'red' };

function parse(line) {
  const m = line.match(/^(\S+)\s+(INFO|WARN|WARNING|ERROR|DEBUG)\s+(.*)$/);
  return m ? { time: m[1], level: m[2], message: m[3] } : { time: '', level: '', message: line };
}

export default function LogViewer({ logs }) {
  const [filter, setFilter] = useState('all');
  const parsed = logs.map(parse);
  const shown = filter === 'all' ? parsed : parsed.filter((l) => l.level && l.level !== 'INFO' && l.level !== 'DEBUG');

  return (
    <Stack gap="sm">
      <SegmentedControl
        w="fit-content"
        size="xs"
        value={filter}
        onChange={setFilter}
        data={[
          { value: 'all', label: `All (${parsed.length})` },
          { value: 'problems', label: `Warnings & errors (${parsed.length - parsed.filter((l) => l.level === 'INFO').length})` },
        ]}
      />
      <Paper withBorder radius="md" p="xs">
        {shown.map((l, i) => (
          <Group key={i} gap="sm" wrap="nowrap" px="xs" py={4} className="log-line" align="flex-start">
            <Text span c="dimmed" className="log-line" style={{ flexShrink: 0 }}>{l.time}</Text>
            {l.level && (
              <Badge size="sm" radius="sm" w={58} color={LEVEL_COLOR[l.level] ?? 'gray'} variant="light" style={{ flexShrink: 0 }}>
                {l.level}
              </Badge>
            )}
            <Text span className="log-line" c={l.level === 'ERROR' ? 'red' : undefined}>{l.message}</Text>
          </Group>
        ))}
      </Paper>
    </Stack>
  );
}
