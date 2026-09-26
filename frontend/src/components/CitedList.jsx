import { Code, List, Text } from '@mantine/core';
import { parseCited } from '../utils';

/** A list of "[evidence.id] text" lines, with the cited evidence ID shown as a code tag. */
export default function CitedList({ items, empty = 'No evidence cited.' }) {
  if (!items?.length) return <Text size="sm" c="dimmed">{empty}</Text>;
  return (
    <List spacing={6} size="sm" style={{ minWidth: 0 }} styles={{ itemWrapper: { minWidth: 0 }, itemLabel: { minWidth: 0 } }}>
      {items.map((line, i) => {
        const { id, text } = parseCited(line);
        return (
          <List.Item key={i} style={{ overflowWrap: 'anywhere' }}>
            {id && <Code mr={6} style={{ overflowWrap: 'anywhere', whiteSpace: 'normal' }}>{id}</Code>}
            {text}
          </List.Item>
        );
      })}
    </List>
  );
}
