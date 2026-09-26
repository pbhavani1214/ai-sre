/**
 * Turns an ApiError (CONTRACT.md §30 structured errors) into what the UI shows: a short title, the backend's
 * message (omitted when it only repeats the title), and where to show it.
 */

// Errors about an uploaded file itself. Shown under the file drop area.
const FILE_ERROR_TITLE = {
  unsupported_file_type: 'Unsupported file type',
  malformed_csv: 'The CSV could not be read',
  empty_file: 'The file is empty',
  missing_header: 'The CSV has no header row',
  file_too_large: 'The file is too large',
  invalid_file: 'The file was rejected',
};

const norm = (s) => String(s ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

/** The backend message, unless it just repeats the title. */
function detailFor(title, message) {
  return message && norm(message) !== norm(title) ? message : null;
}

/** @returns {{slot: 'file'|'form', kind?: string, title: string, message: string|null}} */
export function describeUploadError(error) {
  if (FILE_ERROR_TITLE[error.code] || error.field === 'file') {
    const title = FILE_ERROR_TITLE[error.code] ?? 'The file was rejected';
    return { slot: 'file', title, message: detailFor(title, error.message) };
  }
  const known = {
    target_not_found: ['target', 'This target is no longer available'],
    run_not_found: ['run', 'This run no longer exists'],
    run_not_retryable: ['run', 'This run cannot be retried'],
    network_error: [null, 'Could not reach the backend'],
    backend_not_configured: [null, 'Could not reach the backend'],
  }[error.code];
  const title = known?.[1] ?? 'The run could not be created';
  return { slot: 'form', kind: known?.[0] ?? null, title, message: detailFor(title, error.message) };
}

/** Investigation errors (CONTRACT.md §18) by HTTP status and code. */
export function describeInvestigationError(error) {
  let title;
  if (error.code === 'llm_not_configured' || error.status === 503) title = 'AI investigation is not configured';
  else if (error.code === 'llm_timeout' || error.status === 504) title = 'The AI investigation timed out';
  else if (error.code === 'invalid_ai_response') title = 'The AI returned an invalid response';
  else if (error.code === 'llm_provider_error' || error.status === 502) title = 'The AI provider failed';
  else if (error.status === 409) title = 'This run cannot be investigated';
  else if (error.code === 'run_not_found') title = 'This run no longer exists';
  else if (error.code === 'network_error' || error.code === 'backend_not_configured') title = 'Could not reach the backend';
  else title = 'The investigation failed';
  const hint = {
    'AI investigation is not configured': 'Set LLM_API_KEY for the backend and restart it.',
    'The AI investigation timed out': 'Try again; the provider may be busy.',
    'This run no longer exists': 'Runs are kept in memory and are lost when the backend restarts. Upload the file again.',
  }[title] ?? null;
  return { title, message: detailFor(title, error.message), hint, retryable: error.status !== 409 };
}
