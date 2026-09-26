import { Badge, Card, Tabs, Text, Title } from '@mantine/core';
import { IconDatabase, IconListCheck, IconRoute, IconTerminal2 } from '@tabler/icons-react';
import ValidationChecks from './ValidationChecks';
import PipelineSteps from './PipelineSteps';
import LogViewer from './LogViewer';
import DataCompare from './DataCompare';

export default function EvidenceTabs({ data }) {
  const failed = data.validation_results.filter((v) => !v.passed).length;
  return (
    <Card>
      <Title order={3} fz="lg">Evidence</Title>
      <Text size="sm" c="dimmed" mb="md">
        Deterministic facts gathered from the run. These are computed without AI and are identical every time.
      </Text>
      <Tabs defaultValue="checks">
        <Tabs.List className="scroll-tabs">
          <Tabs.Tab value="checks" leftSection={<IconListCheck size={16} />}>
            Data checks {failed > 0 && <Badge size="xs" color="red" variant="filled" ml={4}>{failed}</Badge>}
          </Tabs.Tab>
          <Tabs.Tab value="pipeline" leftSection={<IconRoute size={16} />}>Pipeline steps</Tabs.Tab>
          <Tabs.Tab value="logs" leftSection={<IconTerminal2 size={16} />}>Logs</Tabs.Tab>
          <Tabs.Tab value="data" leftSection={<IconDatabase size={16} />}>Data</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="checks" pt="md"><ValidationChecks validations={data.validation_results} /></Tabs.Panel>
        <Tabs.Panel value="pipeline" pt="md"><PipelineSteps run={data.pipeline_run} /></Tabs.Panel>
        <Tabs.Panel value="logs" pt="md"><LogViewer logs={data.pipeline_run.logs} /></Tabs.Panel>
        <Tabs.Panel value="data" pt="md"><DataCompare source={data.source} target={data.target} /></Tabs.Panel>
      </Tabs>
    </Card>
  );
}
