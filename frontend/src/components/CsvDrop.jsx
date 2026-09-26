import { ActionIcon, Group, Paper, Stack, Text, ThemeIcon, Tooltip } from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import { IconFileSpreadsheet, IconFileUpload, IconX } from '@tabler/icons-react';
import { formatBytes } from '../utils';

export const MAX_CSV_BYTES = 10 * 1024 * 1024; // CONTRACT.md §11: maximum 10 MB

/**
 * UX guardrails only: a .csv name and the 10 MB limit, so obvious mistakes are caught before uploading.
 * The backend stays authoritative for everything else (encoding, header, rows, schema).
 * @returns {string|null} a message, or null if the file may be uploaded
 */
export function checkCsvFile(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) return `${file.name} is not a CSV file. Choose a .csv file.`;
  if (file.size > MAX_CSV_BYTES) {
    return `${file.name} is ${formatBytes(file.size)}. The maximum is ${formatBytes(MAX_CSV_BYTES)}.`;
  }
  return null;
}

/** A single CSV slot: a drop area that also opens the file picker, or the chosen file with a remove button. */
export default function CsvDrop({ file, error, disabled, onSelect, onRemove }) {
  return (
    <Stack gap={6}>
      {file ? (
        <Paper withBorder p="md" radius="md" style={error ? { borderColor: 'var(--mantine-color-red-6)' } : undefined}>
          <Group justify="space-between" wrap="nowrap" gap="sm">
            <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
              <ThemeIcon size="lg" variant="light" color={error ? 'red' : 'indigo'}><IconFileSpreadsheet size={20} /></ThemeIcon>
              <div style={{ minWidth: 0 }}>
                <Text size="sm" fw={600} truncate="end" data-testid="selected-file-name">{file.name}</Text>
                <Text size="xs" c="dimmed">{formatBytes(file.size)}</Text>
              </div>
            </Group>
            <Tooltip label="Remove file">
              <ActionIcon variant="subtle" color="gray" onClick={onRemove} disabled={disabled} aria-label="Remove file">
                <IconX size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Paper>
      ) : (
        <Dropzone
          onDrop={(files) => files[0] && onSelect(files[0])}
          multiple={false}
          disabled={disabled}
          radius="md"
          p="xl"
          aria-label="CSV file"
          inputProps={{ 'aria-label': 'Choose a CSV file' }}
          style={error ? { borderColor: 'var(--mantine-color-red-6)' } : undefined}
        >
          <Stack align="center" gap={6} style={{ pointerEvents: 'none' }}>
            <ThemeIcon variant="light" size={48} radius="xl"><IconFileUpload size={26} /></ThemeIcon>
            <Text size="sm" ta="center">Drop your CSV here or <Text span c="indigo" fw={500}>browse</Text></Text>
            <Text size="xs" c="dimmed" ta="center">One .csv file with a header row · up to {formatBytes(MAX_CSV_BYTES)}</Text>
          </Stack>
        </Dropzone>
      )}
      {error && <Text size="sm" c="red" role="alert">{error}</Text>}
    </Stack>
  );
}
