import { useRef, useState } from 'react';
import { Alert, Button, Card, Group, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconAlertTriangle, IconFileUpload, IconRefresh } from '@tabler/icons-react';
import CsvDrop, { checkCsvFile } from './CsvDrop';
import { retryRun } from '../services/api';
import { describeUploadError } from '../services/errors';

/**
 * Corrected upload for a failed run: POST /api/runs/{run_id}/retry with ONE CSV. The backend creates a NEW run linked
 * by parent_run_id; this run is left unchanged. The new run is handed to `onRetried`.
 */
export default function RetryPanel({ runId, onRetried }) {
  const [file, setFile] = useState(null);
  const [clientError, setClientError] = useState(null);
  const [serverError, setServerError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);

  const select = (f) => { setFile(f); setClientError(checkCsvFile(f)); setServerError(null); };
  const remove = () => { setFile(null); setClientError(null); setServerError(null); };

  const submit = async () => {
    if (inFlight.current || !file || clientError) return;
    inFlight.current = true;
    setSubmitting(true);
    setServerError(null);
    try {
      onRetried(await retryRun(runId, file));
    } catch (e) {
      setServerError(describeUploadError(e));
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  const fileError = clientError
    ?? (serverError?.slot === 'file'
      ? <><Text span fw={600}>{serverError.title}.</Text>{serverError.message && <> {serverError.message}</>}</>
      : null);

  return (
    <Card data-testid="retry-panel">
      <Group gap="sm" mb="xs">
        <ThemeIcon size="lg" radius="md" variant="light" color="teal"><IconFileUpload size={20} /></ThemeIcon>
        <Title order={2} fz="lg">Fix the data and retry</Title>
      </Group>
      <Text size="sm" c="dimmed" mb="md">
        Correct the CSV using the evidence above, then upload the corrected file. This creates a new run linked to
        this one; this run stays unchanged.
      </Text>
      <Stack gap="md">
        {serverError?.slot === 'form' && (
          <Alert color="red" variant="light" icon={<IconAlertTriangle />} title={serverError.title} role="alert">
            {serverError.message && <Text size="sm">{serverError.message}</Text>}
          </Alert>
        )}
        <CsvDrop file={file} error={fileError} disabled={submitting} onSelect={select} onRemove={remove} />
        <Group justify="flex-end">
          <Button leftSection={<IconRefresh size={16} />} onClick={submit} disabled={!file || Boolean(clientError)} loading={submitting}>
            Retry with corrected file
          </Button>
        </Group>
        {submitting && <Text size="sm" c="dimmed" aria-live="polite">Uploading {file.name} and creating a new run…</Text>}
      </Stack>
    </Card>
  );
}
