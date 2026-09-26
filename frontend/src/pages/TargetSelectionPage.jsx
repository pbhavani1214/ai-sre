import { useState } from 'react';
import {
  Alert, Button, Card, Container, Group, Loader, Select, SimpleGrid, Skeleton, Stack, Text, ThemeIcon, Title, Tooltip,
} from '@mantine/core';
import { IconAlertTriangle, IconArrowRight, IconDatabase, IconRefresh } from '@tabler/icons-react';
import TargetSchema from '../components/TargetSchema';
import { useTargetDetail, useTargets } from '../hooks/useTargets';
import { databaseLabel } from '../utils';


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

export default function TargetSelectionPage({ initialTargetId = null, onContinue }) {
  const targets = useTargets();
  const [selectedId, setSelectedId] = useState(initialTargetId);
  const detail = useTargetDetail(selectedId);

  const selected = targets.data?.find((t) => t.target_id === selectedId) ?? null;
  // Continue only once the schema for the current selection has loaded without error.
  const canContinue = Boolean(selected && detail.data?.target_id === selected.target_id && !detail.loading && !detail.error);
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
            Pick the table to load. Your CSV will be validated against its schema and constraints before anything
            is written, and failures are investigated by the AI.
          </Text>
        </div>

        <Card>
          <Stack gap="md">
            <Group gap="sm">
              <ThemeIcon size="lg" radius="md" variant="light"><IconDatabase size={20} /></ThemeIcon>
              <Title order={2} fz="lg">Select target</Title>
            </Group>

            {targets.loading && (
              <Group gap="xs" aria-busy="true"><Loader size="xs" /><Text size="sm" c="dimmed">Loading targets…</Text></Group>
            )}
            {targets.error && (
              <ErrorAlert title="Could not load the target tables" error={targets.error} onRetry={targets.reload} />
            )}
            {targets.data && targets.data.length === 0 && (
              <Alert color="gray" variant="light" title="No target tables">
                The backend has no target tables configured.
              </Alert>
            )}
            {targets.data && targets.data.length > 0 && (
              <Select
                label="Target table"
                placeholder="Choose a target table"
                data={targets.data.map((t) => ({ value: t.target_id, label: t.display_name }))}
                value={selectedId}
                onChange={setSelectedId}
                allowDeselect={false}
                checkIconPosition="right"
                comboboxProps={{ withinPortal: false }}
              />
            )}

            {selected && (
              <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="md">
                <Fact label="Target">{selected.display_name}</Fact>
                <Fact label="Table"><Text span ff="monospace" size="sm">{selected.table_name}</Text></Fact>
                <Fact label="Database">{databaseLabel(selected.database_type)}</Fact>
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
          <Tooltip label="Select a target and wait for its schema to load" disabled={canContinue}>
            {/* A disabled button fires no mouse events, so the tooltip needs a wrapper. */}
            <span>
              <Button rightSection={<IconArrowRight size={16} />} disabled={!canContinue} onClick={() => onContinue(selected)}>
                Continue
              </Button>
            </span>
          </Tooltip>
        </Group>
      </Stack>
    </Container>
  );
}
