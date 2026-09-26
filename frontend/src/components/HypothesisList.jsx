import { Accordion, Badge, Group, Stack, Text } from '@mantine/core';
import { IconCheck, IconQuestionMark, IconX } from '@tabler/icons-react';
import CitedList from './CitedList';

const STATUS = {
  SUPPORTED: { color: 'green', label: 'Supported', icon: IconCheck },
  REJECTED: { color: 'gray', label: 'Rejected', icon: IconX },
  INCONCLUSIVE: { color: 'yellow', label: 'Inconclusive', icon: IconQuestionMark },
};
const ORDER = { SUPPORTED: 0, INCONCLUSIVE: 1, REJECTED: 2 };

export default function HypothesisList({ hypotheses }) {
  const sorted = [...hypotheses].sort((a, b) => (ORDER[a.status] ?? 1) - (ORDER[b.status] ?? 1));

  return (
    <Accordion variant="separated" radius="md" multiple defaultValue={['0']}>
      {sorted.map((h, i) => {
        const s = STATUS[h.status] ?? { color: 'yellow', label: h.status, icon: IconQuestionMark };
        return (
          <Accordion.Item key={i} value={String(i)}>
            <Accordion.Control>
              <Group gap="xs" wrap="nowrap" align="flex-start">
                <Badge color={s.color} variant="light" leftSection={<s.icon size={12} />} style={{ flexShrink: 0 }}>
                  {s.label}
                </Badge>
                <Text size="sm" fw={500} c={h.status === 'REJECTED' ? 'dimmed' : undefined}>{h.hypothesis}</Text>
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap="md">
                <div>
                  <Text size="xs" fw={600} tt="uppercase" c="dimmed" mb={6}>Reasoning</Text>
                  <Text size="sm">{h.reasoning}</Text>
                </div>
                <div>
                  <Text size="xs" fw={600} tt="uppercase" c="dimmed" mb={6}>Evidence</Text>
                  <CitedList items={h.evidence} />
                </div>
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        );
      })}
    </Accordion>
  );
}
