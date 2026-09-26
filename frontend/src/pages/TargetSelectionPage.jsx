import { useState } from 'react';
import {
  Alert, Button, Card, Container, Group, Loader, Select, SimpleGrid, Skeleton, Stack, Text, ThemeIcon, Title, Tooltip,
} from '@mantine/core';
import { IconAlertTriangle, IconArrowRight, IconDatabase, IconRefresh } from '@tabler/icons-react';
import TargetSchema from '../components/TargetSchema';
import { useDatabases, useTargetDetail, useTargets } from '../hooks/useTargets';


function Fact({ label, children }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
      <Text size="sm" fw={500} style={{ overflowWrap: 'anywhere' }}>{children}</Text>
    </div>
  );
}

function ErrorAlert({ title, error, onRetry }) {
  return (
    <Alert color="red" variant="light" icon={<IconAlertTriangle />} title={title} role="alert">
      <Text size="sm">{error.message}</Text>
      {onRetry && (
        <Button mt="sm" size="xs" color="red" variant="light" leftSection={<IconRefresh size={14} />} onClick={onRetry}>
          Try again
        </Button>
      )}
    </Alert>
  );
}

function SchemaSection({ target, detail, onReloadTargets }) {
  if (detail.loading) {
    return (
      <Stack gap="sm" aria-busy="true">
        <Group gap="xs"><Loader size="xs" /><Text size="sm" c="dimmed">Loading target schema…</Text></Group>
        <Skeleton h={180} radius="md" />
      </Stack>
    );
  }
  if (detail.error) {
    if (detail.error.code === 'target_not_found') {
      return (
        <Alert color="yellow" variant="light" icon={<IconAlertTriangle />} title="This target is no longer available" role="alert">
          <Text size="sm">{detail.error.message}</Text>
          <Button mt="sm" size="xs" variant="light" color="yellow" leftSection={<IconRefresh size={14} />} onClick={onReloadTargets}>
            Reload targets
          </Button>
        </Alert>
      );
    }
    return <ErrorAlert title={`Could not load the schema for ${target.display_name}`} error={detail.error} onRetry={detail.reload} />;
  }
  return detail.data ? <TargetSchema detail={detail.data} /> : null;
}

const databaseOption = (d) => ({
  value: d.database_id,
  label: `${d.display_name} (${d.file_name})${d.is_default ? ' · default' : ''}`,
});
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

export default function TargetSelectionPage({ initialDatabaseId = null, initialTargetId = null, onContinue }) {
  const databases = useDatabases();
  const [databaseId, setDatabaseId] = useState(initialDatabaseId);
  const targets = useTargets(databaseId);
  const [selectedId, setSelectedId] = useState(initialTargetId);
  const detail = useTargetDetail(selectedId, databaseId);

  const database = databases.data?.find((d) => d.database_id === databaseId) ?? null;
  const selected = targets.data?.find((t) => t.target_id === selectedId) ?? null;
  // Continue only once the schema for the current selection has loaded without error.
  const canContinue = Boolean(database && selected && detail.data?.target_id === selected.target_id
    && !detail.loading && !detail.error);
  const chooseDatabase = (id) => {
    if (id === databaseId) return;
    setDatabaseId(id);
    setSelectedId(null); // tables belong to one database
  };
  const reloadTargets = () => {
    setSelectedId(null);
    targets.reload();
  };

  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={1} fz={{ base: 26, sm: 32 }}>Load data into a target table</Title>
          <Text c="dimmed" mt="xs">
            Pick the database and the table to load. Your CSV will be validated against the table&apos;s schema and
            constraints before anything is written, and failures are investigated by the AI.
          </Text>
        </div>

        <Card>
          <Stack gap="md">
            <Group gap="sm">
              <ThemeIcon size="lg" radius="md" variant="light"><IconDatabase size={20} /></ThemeIcon>
              <Title order={2} fz="lg">Select target</Title>
            </Group>

            {databases.loading && (
              <Group gap="xs" aria-busy="true"><Loader size="xs" /><Text size="sm" c="dimmed">Loading databases…</Text></Group>
            )}
            {databases.error && (
              <ErrorAlert title="Could not load the databases" error={databases.error} onRetry={databases.reload} />
            )}
            {databases.data && databases.data.length === 0 && (
              <Alert color="gray" variant="light" title="No databases">The backend found no SQLite databases.</Alert>
            )}
            {databases.data && databases.data.length > 0 && (
              <Select
                label="Database"
                placeholder="Choose a database"
                data={databases.data.map(databaseOption)}
                value={databaseId}
                onChange={chooseDatabase}
                allowDeselect={false}
                checkIconPosition="right"
              />
            )}

            {database && targets.loading && (
              <Group gap="xs" aria-busy="true"><Loader size="xs" /><Text size="sm" c="dimmed">Loading tables…</Text></Group>
            )}
            {database && targets.error && (
              <ErrorAlert title={`Could not load the tables of ${database.display_name}`} error={targets.error}
                onRetry={targets.reload} />
            )}
            {database && targets.data && targets.data.length === 0 && (
              <Alert color="gray" variant="light" title="No tables">{database.file_name} has no tables to load into.</Alert>
            )}
            {database && targets.data && targets.data.length > 0 && (
              <Select
                label="Target table"
                description={`${plural(targets.data.length, 'table')} in ${database.display_name}`}
                placeholder="Choose a target table"
                data={targets.data.map((t) => ({ value: t.target_id, label: t.display_name }))}
                value={selectedId}
                onChange={setSelectedId}
                allowDeselect={false}
                checkIconPosition="right"
              />
            )}

            {database && selected && (
              <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="md">
                <Fact label="Database">
                  {database.display_name}{' '}
                  <Text span size="xs" c="dimmed" ff="monospace">({database.file_name})</Text>
                </Fact>
                <Fact label="Target">{selected.display_name}</Fact>
                <Fact label="Table"><Text span ff="monospace" size="sm">{selected.table_name}</Text></Fact>
              </SimpleGrid>
            )}
            {selected?.description && <Fact label="Description">{selected.description}</Fact>}
          </Stack>
        </Card>

        {selected && (
          <Card>
            <Title order={3} fz="lg" mb="md">
              Schema of <Text span ff="monospace" fz="lg" fw={650}>{selected.table_name}</Text>
            </Title>
            <SchemaSection target={selected} detail={detail} onReloadTargets={reloadTargets} />
          </Card>
        )}

        <Group justify="flex-end">
          <Tooltip label="Select a database and a table, and wait for its schema to load" disabled={canContinue}>
            {/* A disabled button fires no mouse events, so the tooltip needs a wrapper. */}
            <span>
              <Button rightSection={<IconArrowRight size={16} />} disabled={!canContinue} onClick={() => onContinue({ database, target: selected })}>
                Continue
              </Button>
            </span>
          </Tooltip>
        </Group>
      </Stack>
    </Container>
  );
}
