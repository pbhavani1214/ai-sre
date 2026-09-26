import { useRef, useState } from 'react';
import {
  Alert, Anchor, Button, Card, Container, Group, SimpleGrid, Stack, Text, ThemeIcon, Title,
} from '@mantine/core';
import { IconAlertTriangle, IconArrowLeft, IconDatabase, IconPlayerPlay } from '@tabler/icons-react';
import CsvDrop, { checkCsvFile } from '../components/CsvDrop';
import { createRun } from '../services/api';
import { databaseLabel } from '../utils';

// Backend errors about the uploaded file itself (CONTRACT.md §30). Shown under the drop area.
const FILE_ERROR_TITLE = {
  unsupported_file_type: 'Unsupported file type',
  malformed_csv: 'The CSV could not be read',
  empty_file: 'The file is empty',
  missing_header: 'The CSV has no header row',
  file_too_large: 'The file is too large',
  invalid_file: 'The file was rejected',
};

function Fact({ label, children }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
      <Text size="sm" fw={500} style={{ overflowWrap: 'anywhere' }}>{children}</Text>
    </div>
  );
}

/** Where a failed POST /api/runs is shown: under the file, or in an alert above the form. */
function describeError(error) {
  if (FILE_ERROR_TITLE[error.code] || error.field === 'file') {
    return { slot: 'file', title: FILE_ERROR_TITLE[error.code] ?? 'The file was rejected', message: error.message };
  }
  if (error.code === 'target_not_found') {
    return { slot: 'form', kind: 'target', title: 'This target is no longer available', message: error.message };
  }
  if (error.code === 'network_error' || error.code === 'backend_not_configured') {
    return { slot: 'form', title: 'Could not reach the backend', message: error.message };
  }
  return { slot: 'form', title: 'The run could not be created', message: error.message };
}

export default function UploadPage({ target, onBack, onCreated }) {
  const [file, setFile] = useState(null);
  const [clientError, setClientError] = useState(null);
  const [serverError, setServerError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false); // guards against a second submit before React re-renders

  const select = (f) => {
    setFile(f);
    setClientError(checkCsvFile(f));
    setServerError(null);
  };
  const remove = () => {
    setFile(null);
    setClientError(null);
    setServerError(null);
  };

  const submit = async () => {
    if (inFlight.current || !file || clientError) return;
    inFlight.current = true;
    setSubmitting(true);
    setServerError(null);
    try {
      const run = await createRun(target.target_id, file);
      onCreated(run);
    } catch (e) {
      setServerError(describeError(e));
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  const fileError = clientError
    ?? (serverError?.slot === 'file' ? <><Text span fw={600}>{serverError.title}.</Text> {serverError.message}</> : null);

  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <div>
          <Anchor component="button" size="sm" onClick={onBack} disabled={submitting}>
            <Group gap={4}><IconArrowLeft size={14} /> Back to target selection</Group>
          </Anchor>
          <Title order={1} fz={{ base: 26, sm: 32 }} mt="xs">Upload a CSV</Title>
          <Text c="dimmed" mt="xs">
            Upload one CSV to load into this table. Creating the run sends the file to the backend, which checks it
            against the table&apos;s schema and constraints.
          </Text>
        </div>

        <Card>
          <Group gap="sm" mb="md">
            <ThemeIcon size="lg" radius="md" variant="light"><IconDatabase size={20} /></ThemeIcon>
            <Title order={2} fz="lg">Target</Title>
          </Group>
          <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="md">
            <Fact label="Target">{target.display_name}</Fact>
            <Fact label="Table"><Text span ff="monospace" size="sm">{target.table_name}</Text></Fact>
            <Fact label="Database">{databaseLabel(target.database_type)}</Fact>
          </SimpleGrid>
        </Card>

        {serverError?.slot === 'form' && (
          <Alert color="red" variant="light" icon={<IconAlertTriangle />} title={serverError.title} role="alert">
            <Text size="sm">{serverError.message}</Text>
            {serverError.kind === 'target' && (
              <Button mt="sm" size="xs" color="red" variant="light" onClick={onBack}>Choose another target</Button>
            )}
          </Alert>
        )}

        <Card>
          <Stack gap="md">
            <div>
              <Title order={2} fz="lg">Data file</Title>
              <Text size="sm" c="dimmed">CSV only, UTF-8, with a header row · maximum 10 MB · one file</Text>
            </div>
            <CsvDrop file={file} error={fileError} disabled={submitting} onSelect={select} onRemove={remove} />
            <Group justify="space-between">
              <Button variant="default" leftSection={<IconArrowLeft size={16} />} onClick={onBack} disabled={submitting}>
                Back
              </Button>
              <Button
                leftSection={<IconPlayerPlay size={16} />}
                onClick={submit}
                disabled={!file || Boolean(clientError)}
                loading={submitting}
              >
                Create run
              </Button>
            </Group>
            {submitting && <Text size="sm" c="dimmed" aria-live="polite">Uploading {file.name} and creating the run…</Text>}
          </Stack>
        </Card>
      </Stack>
    </Container>
  );
}
