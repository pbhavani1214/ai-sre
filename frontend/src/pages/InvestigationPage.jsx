import { useRef } from 'react';
import { Alert, Button, Container, Skeleton, Stack } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useScenario } from '../hooks/useScenario';
import { useInvestigation } from '../hooks/useInvestigation';
import RunOverview from '../components/RunOverview';
import InvestigationPanel from '../components/InvestigationPanel';
import EvidenceTabs from '../components/EvidenceTabs';

export default function InvestigationPage() {
  const scenario = useScenario();
  const investigation = useInvestigation();
  const panelRef = useRef(null);

  const startInvestigation = () => {
    investigation.start(scenario.data);
    panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (scenario.loading) {
    return (
      <Container size="lg" py="md">
        <Stack>
          <Skeleton h={220} radius="lg" />
          <Skeleton h={160} radius="lg" />
          <Skeleton h={320} radius="lg" />
        </Stack>
      </Container>
    );
  }

  if (scenario.error) {
    return (
      <Container size="sm" py="xl">
        <Alert color="red" title="Could not load the pipeline run" icon={<IconAlertTriangle />}>
          {scenario.error.message}
          <Button mt="md" variant="light" color="red" onClick={scenario.reload}>Try again</Button>
        </Alert>
      </Container>
    );
  }

  const data = scenario.data;
  return (
    <Container size="lg" py="md">
      <Stack gap="lg">
        <RunOverview
          scenario={data}
          investigationStatus={investigation.status}
          onInvestigate={startInvestigation}
        />
        <div ref={panelRef} style={{ scrollMarginTop: 76 }}>
          <InvestigationPanel
            {...investigation}
            validations={data.validation_results}
            onStart={startInvestigation}
          />
        </div>
        <EvidenceTabs data={data} />
      </Stack>
    </Container>
  );
}
