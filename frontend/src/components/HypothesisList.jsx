import { Accordion, Badge, Group, List, Progress, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconCheck, IconMinus, IconQuestionMark, IconX } from '@tabler/icons-react';

const STATUS = {
  confirmed: { color: 'green', label: 'Confirmed', icon: IconCheck },
  rejected: { color: 'gray', label: 'Rejected', icon: IconX },
  inconclusive: { color: 'yellow', label: 'Inconclusive', icon: IconQuestionMark },
};
const ORDER = { confirmed: 0, inconclusive: 1, rejected: 2 };

function EvidenceList({ title, items, color, icon: Icon }) {
  if (!items?.length) return null;
  return (
    <div>
      <Text size="xs" fw={600} tt="uppercase" c="dimmed" mb={6}>{title}</Text>
      <List
        spacing={6}
        size="sm"
        icon={<ThemeIcon color={color} size={18} radius="xl" variant="light"><Icon size={12} /></ThemeIcon>}
      >
        {items.map((e, i) => <List.Item key={i}>{e}</List.Item>)}
      </List>
    </div>
  );
}

export default function HypothesisList({ hypotheses }) {
  const sorted = [...hypotheses].sort(
    (a, b) => (ORDER[a.status] ?? 1) - (ORDER[b.status] ?? 1) || b.confidence - a.confidence,
  );

  return (
    <Accordion variant="separated" radius="md" multiple defaultValue={['0']}>
      {sorted.map((h, i) => {
        const s = STATUS[h.status] ?? { color: 'yellow', label: h.status, icon: IconQuestionMark };
        const pct = Math.round(h.confidence * 100);
        return (
          <Accordion.Item key={i} value={String(i)}>
            <Accordion.Control>
              <Stack gap={6}>
                <Group gap="xs" wrap="nowrap" align="flex-start">
                  <Badge color={s.color} variant="light" leftSection={<s.icon size={12} />} style={{ flexShrink: 0 }}>
                    {s.label}
                  </Badge>
                  <Text size="sm" fw={500} c={h.status === 'rejected' ? 'dimmed' : undefined}>{h.statement}</Text>
                </Group>
                <Group gap="xs" wrap="nowrap">
                  <Progress value={pct} color={s.color} size="sm" w={140} aria-label={`Confidence ${pct}%`} />
                  <Text size="xs" c="dimmed">{pct}% confidence</Text>
                </Group>
              </Stack>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap="md">
                <EvidenceList title="Supporting evidence" items={h.supporting_evidence} color="green" icon={IconCheck} />
                <EvidenceList title="Contradicting evidence" items={h.contradicting_evidence} color="red" icon={IconMinus} />
                {!h.supporting_evidence?.length && !h.contradicting_evidence?.length && (
                  <Text size="sm" c="dimmed">No evidence cited.</Text>
                )}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        );
      })}
    </Accordion>
  );
}
