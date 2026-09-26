import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RunResultPage from './RunResultPage';
import { deferred, mockFetch, renderWithMantine } from '../test/utils';

const TARGET = { target_id: 'ledger', table_name: 'ledger_entries', display_name: 'Ledger entries', database_type: 'sqlite' };
const FAILED = { name: 'amount_limit', status: 'FAILED', severity: 'ERROR', summary: 'Amounts above the limit.',
  metrics: { affected_rows: 1 }, evidence: ['[validation.amount_limit.001] amount=999999 exceeds configured limit'] };
const base = {
  run_id: 'run_aaaaaaaaaaaa', parent_run_id: null, target_id: 'ledger', target_table: 'ledger_entries',
  file_name: 'ledger.csv', created_at: '2026-09-26T10:30:00Z', completed_at: '2026-09-26T10:30:02Z',
};
const FAILED_RUN = { ...base, status: 'FAILED_VALIDATION', load_result: null, validation_results: [FAILED],
  summary: { rows_received: 12, checks_total: 1, checks_passed: 0, checks_failed: 1 } };

const INVESTIGATION = {
  run_id: 'run_aaaaaaaaaaaa',
  summary: 'The upload violates the ledger amount limit.',
  observed_facts: ['[validation.amount_limit] amount=999999 exceeds configured limit'],
  hypotheses: [
    { hypothesis: 'The export multiplies amounts by 100.', status: 'SUPPORTED',
      evidence: ['[validation.amount_limit] amount=999999'], reasoning: 'The value is 100x a normal amount.' },
    { hypothesis: 'The database is unavailable.', status: 'REJECTED', evidence: [], reasoning: 'Validation ran against the schema.' },
  ],
  root_cause_status: 'IDENTIFIED',
  root_cause: 'Amounts are exported in cents instead of units.',
  root_cause_evidence: ['[validation.amount_limit] amount=999999 exceeds configured limit'],
  root_cause_reasoning: 'Only the amount check fails and the value is 100x the limit scale.',
  recommended_fix: 'Divide amount by 100 in the export before retrying.',
  regression_test: 'def test_amount_within_limit():\n    assert amount <= 50000',
  investigation_trace: [{ stage: 'evidence_review', description: 'Reviewed 1 failed check.' }],
  evidence_warnings: [],
};

function renderRun(run, props = {}) {
  const handlers = {
    onInvestigation: vi.fn(), onRetried: vi.fn(), onOpenRun: vi.fn(), onUploadAnother: vi.fn(), onChooseTarget: vi.fn(),
  };
  const utils = renderWithMantine(<RunResultPage run={run} target={TARGET} investigation={null} {...handlers} {...props} />);
  return { ...handlers, ...utils, user: userEvent.setup() };
}

describe('SUCCEEDED and LOAD_FAILED', () => {
  it('shows a success state with every load_result value from the backend', () => {
    renderRun({ ...base, status: 'SUCCEEDED', validation_results: [],
      summary: { rows_received: 12, checks_total: 6, checks_passed: 6, checks_failed: 0 },
      load_result: { rows_attempted: 12, rows_inserted: 12, target_table: 'ledger_entries' } });
    expect(screen.getByRole('heading', { name: 'Loaded successfully' })).toBeInTheDocument();
    const card = screen.getByTestId('load-result');
    expect(within(card).getByText('Rows attempted')).toBeInTheDocument();
    expect(within(card).getByTestId('load-rows_attempted')).toHaveTextContent('12');
    expect(within(card).getByTestId('load-rows_inserted')).toHaveTextContent('12');
    expect(within(card).getByTestId('load-target_table')).toHaveTextContent('ledger_entries');
    expect(within(card).getByText('Completed')).toBeInTheDocument();
    expect(screen.queryByTestId('investigation')).not.toBeInTheDocument();
    expect(screen.queryByTestId('retry-panel')).not.toBeInTheDocument();
  });

  it('renders the contract field rows_loaded the same way', () => {
    renderRun({ ...base, status: 'SUCCEEDED', validation_results: [],
      summary: { rows_received: 7, checks_total: 7, checks_passed: 7, checks_failed: 0 },
      load_result: { rows_loaded: 7, target_table: 'ledger_entries' } });
    expect(screen.getByTestId('load-rows_loaded')).toHaveTextContent('7');
  });

  it('distinguishes a load failure from a validation failure and offers investigate and retry', () => {
    renderRun({ ...base, status: 'LOAD_FAILED', validation_results: [],
      summary: { rows_received: 12, checks_total: 6, checks_passed: 6, checks_failed: 0 },
      load_result: { rows_attempted: 12, rows_inserted: 0, error: 'UNIQUE constraint failed: ledger_entries.entry_id' } });
    expect(screen.getByRole('heading', { name: 'Load failed' })).toBeInTheDocument();
    expect(screen.getByText(/Validation passed, but the database load failed and was rolled back/)).toBeInTheDocument();
    expect(screen.getByTestId('load-error')).toHaveTextContent('UNIQUE constraint failed: ledger_entries.entry_id');
    expect(screen.queryByText('Loaded successfully')).not.toBeInTheDocument();
    expect(screen.getByTestId('investigation')).toBeInTheDocument();
    expect(screen.getByTestId('retry-panel')).toBeInTheDocument();
  });

  it('never says loaded for a failed or not-yet-loaded run', () => {
    for (const status of ['FAILED_VALIDATION', 'LOADING', 'CREATED']) {
      const { unmount } = renderRun({ ...FAILED_RUN, status });
      expect(screen.queryByText(/loaded successfully/i)).not.toBeInTheDocument();
      expect(screen.queryByTestId('load-result')).not.toBeInTheDocument();
      unmount();
    }
  });
});

describe('run-scoped investigation', () => {
  it('calls POST /api/runs/{run_id}/investigate for this run, shows progress, then hands back the result', async () => {
    const pending = deferred();
    const fetch = mockFetch({ 'POST /api/runs/run_aaaaaaaaaaaa/investigate': () => pending.promise });
    const { user, onInvestigation } = renderRun(FAILED_RUN);

    await user.click(screen.getByRole('button', { name: 'Investigate with AI' }));
    expect(await screen.findByText('Investigating this run…')).toBeInTheDocument();
    await user.click(screen.queryByRole('button', { name: 'Investigate with AI' }) ?? document.body);
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('http://api.test/api/runs/run_aaaaaaaaaaaa/investigate');
    expect(init.method).toBe('POST');
    expect(init.body).toBeUndefined();

    pending.resolve([200, INVESTIGATION]);
    await waitFor(() => expect(onInvestigation).toHaveBeenCalledWith(INVESTIGATION));
  });

  it('renders every investigation section from the response', async () => {
    const { user } = renderRun(FAILED_RUN, { investigation: INVESTIGATION });
    const panel = screen.getByTestId('investigation');
    for (const text of [INVESTIGATION.summary, INVESTIGATION.root_cause, INVESTIGATION.root_cause_reasoning, INVESTIGATION.recommended_fix,
      'The export multiplies amounts by 100.', 'The database is unavailable.', 'Root cause reasoning', 'Root cause evidence']) {
      expect(within(panel).getAllByText(text).length).toBeGreaterThan(0);
    }
    expect(within(panel).getByText('Identified')).toBeInTheDocument();
    await user.click(within(panel).getByRole('tab', { name: /Evidence reviewed/ }));
    expect(within(panel).getAllByText('amount=999999 exceeds configured limit').length).toBeGreaterThan(0);
    await user.click(within(panel).getByRole('tab', { name: /Trace/ }));
    expect(within(panel).getByText('Reviewed 1 failed check.')).toBeInTheDocument();
    await user.click(within(panel).getByRole('tab', { name: /Regression test/ }));
    expect(within(panel).getByText(/def test_amount_within_limit/)).toBeInTheDocument();
  });

  it.each([
    [503, 'llm_not_configured', 'AI investigation is not configured', true],
    [504, 'llm_timeout', 'The AI investigation timed out', true],
    [502, 'invalid_ai_response', 'The AI returned an invalid response', true],
    [502, 'llm_provider_error', 'The AI provider failed', true],
    [409, 'run_not_investigable', 'This run cannot be investigated', false],
  ])('shows %s %s as a clear message', async (status, code, title, retryable) => {
    mockFetch({
      'POST /api/runs/run_aaaaaaaaaaaa/investigate': () => [status, { detail: { code, message: `Backend: ${code} details.`, field: null } }],
    });
    const { user } = renderRun(FAILED_RUN);
    await user.click(screen.getByRole('button', { name: 'Investigate with AI' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(title);
    expect(alert).toHaveTextContent(`Backend: ${code} details.`);
    expect(alert).not.toHaveTextContent('{');
    expect(Boolean(within(alert).queryByRole('button', { name: 'Try again' }))).toBe(retryable);
  });

  it('does not repeat a message that only restates the title', async () => {
    mockFetch({
      'POST /api/runs/run_aaaaaaaaaaaa/investigate': () => [503, { detail: { code: 'llm_not_configured', message: 'AI investigation is not configured.', field: null } }],
    });
    const { user } = renderRun(FAILED_RUN);
    await user.click(screen.getByRole('button', { name: 'Investigate with AI' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent.match(/AI investigation is not configured/g)).toHaveLength(1);
  });
});

describe('corrected upload (retry)', () => {
  it('POSTs exactly one file to /api/runs/{run_id}/retry and hands back the new child run', async () => {
    const child = { ...base, run_id: 'run_bbbbbbbbbbbb', parent_run_id: 'run_aaaaaaaaaaaa', status: 'SUCCEEDED',
      validation_results: [], summary: { rows_received: 12, checks_total: 1, checks_passed: 1, checks_failed: 0 },
      load_result: { rows_loaded: 12, target_table: 'ledger_entries' } };
    const fetch = mockFetch({ 'POST /api/runs/run_aaaaaaaaaaaa/retry': () => [201, child] });
    const { user, onRetried } = renderRun(FAILED_RUN);

    const panel = screen.getByTestId('retry-panel');
    await user.upload(within(panel).getByLabelText('Choose a CSV file'), new File(['entry_id\n1\n'], 'ledger_fixed.csv', { type: 'text/csv' }));
    await user.click(within(panel).getByRole('button', { name: 'Retry with corrected file' }));

    await waitFor(() => expect(onRetried).toHaveBeenCalledWith(child));
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('http://api.test/api/runs/run_aaaaaaaaaaaa/retry');
    expect([...init.body.keys()]).toEqual(['file']);
    expect(init.body.get('file').name).toBe('ledger_fixed.csv');
  });

  it('shows run_not_retryable without leaving the page', async () => {
    mockFetch({
      'POST /api/runs/run_aaaaaaaaaaaa/retry': () => [409, { detail: { code: 'run_not_retryable', message: 'Only failed runs can be retried.', field: 'run_id' } }],
    });
    const { user, onRetried } = renderRun(FAILED_RUN);
    const panel = screen.getByTestId('retry-panel');
    await user.upload(within(panel).getByLabelText('Choose a CSV file'), new File(['a\n1\n'], 'x.csv', { type: 'text/csv' }));
    await user.click(within(panel).getByRole('button', { name: 'Retry with corrected file' }));
    const alert = await within(panel).findByRole('alert');
    expect(alert).toHaveTextContent('This run cannot be retried');
    expect(alert).toHaveTextContent('Only failed runs can be retried.');
    expect(onRetried).not.toHaveBeenCalled();
  });

  it('shows the parent link on a child run', async () => {
    const { user, onOpenRun } = renderRun({ ...FAILED_RUN, run_id: 'run_cccccccccccc', parent_run_id: 'run_aaaaaaaaaaaa' });
    const link = screen.getByTestId('parent-link');
    expect(link).toHaveTextContent('run_aaaaaaaaaaaa');
    await user.click(within(link).getByRole('button', { name: 'View original run' }));
    expect(onOpenRun).toHaveBeenCalledWith('run_aaaaaaaaaaaa');
  });
});

describe('investigation fixes (v2.2)', () => {
  const GUIDED = {
    ...INVESTIGATION,
    model: 'gpt-4o',
    cause_groups: [{ title: 'Export writes cents', category: 'SOURCE_FORMAT', explanation: 'Amounts are 100x too large.',
      checks: ['amount_limit'], rows: [3], evidence: ['[dataset.column_profiles] amounts'] }],
    row_fixes: [
      { row: 3, column: 'amount', action: 'REPLACE', current_value: '999999', suggested_value: '9999.99',
        reason: 'Divide by 100.', confidence: 'HIGH', evidence: '[validation.amount_limit.001]', satisfies_constraints: true },
      { row: 5, column: 'memo', action: 'NEEDS_DECISION', current_value: '', suggested_value: null,
        reason: 'The memo is unknown.', confidence: 'LOW', evidence: '', satisfies_constraints: false },
    ],
    prevention: ['Export amounts in units, not cents.'],
    regression_test: '"""Data check for table `ledger_entries` in ledger.db, generated from its schema."""\ndef test_x(): pass',
  };

  it('leads with the root cause, its causes, the row fixes and prevention', () => {
    renderRun(FAILED_RUN, { investigation: GUIDED });
    const panel = screen.getByTestId('investigation');
    expect(within(panel).getByTestId('investigation-model')).toHaveTextContent('gpt-4o');
    expect(within(screen.getByTestId('cause-groups')).getByText('Export writes cents')).toBeInTheDocument();
    const fixes = within(screen.getByTestId('row-fixes')).getByRole('table', { name: 'Suggested fixes' });
    expect(within(fixes).getByText('9999.99')).toBeInTheDocument();
    expect(within(fixes).getByText('Decide')).toBeInTheDocument();
    expect(screen.getByText(/1 value needs your decision/)).toBeInTheDocument();
    expect(within(screen.getByTestId('fix-this-file')).getByText(GUIDED.recommended_fix)).toBeInTheDocument();
    expect(within(screen.getByTestId('prevention')).getByText('Export amounts in units, not cents.')).toBeInTheDocument();
  });

  it('retries with the suggested CSV from the backend', async () => {
    const fetchMock = mockFetch({
      'GET /api/runs/run_aaaaaaaaaaaa/suggested-csv': () => new Response('amount\n9999.99\n', { status: 200, headers: { 'content-type': 'text/csv' } }),
      'POST /api/runs/run_aaaaaaaaaaaa/retry': () => [201, { ...FAILED_RUN, run_id: 'run_bbbbbbbbbbbb', parent_run_id: 'run_aaaaaaaaaaaa' }],
    });
    const { user, onRetried } = renderRun(FAILED_RUN, { investigation: GUIDED });
    await user.click(screen.getByRole('button', { name: 'Retry with suggested CSV' }));
    await waitFor(() => expect(onRetried).toHaveBeenCalledWith(expect.objectContaining({ run_id: 'run_bbbbbbbbbbbb' })));
    const [, init] = fetchMock.mock.calls.find(([url]) => url.endsWith('/retry'));
    const file = init.body.get('file');
    expect(file.name).toBe('ledger_suggested.csv');
    expect(await file.text()).toBe('amount\n9999.99\n');
  });

  it('shows the backend error when no suggested file can be built', async () => {
    mockFetch({
      'GET /api/runs/run_aaaaaaaaaaaa/suggested-csv': () => [409, { detail: { code: 'no_suggested_fixes', message: 'The investigation has no fixes that can be applied automatically.', field: 'run_id' } }],
    });
    const { user } = renderRun(FAILED_RUN, { investigation: GUIDED });
    await user.click(screen.getByRole('button', { name: 'Download suggested CSV' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('no fixes that can be applied automatically');
  });

  it('labels a schema-generated regression test and offers it as a file', async () => {
    const { user } = renderRun(FAILED_RUN, { investigation: GUIDED });
    await user.click(screen.getByRole('tab', { name: /Regression test/ }));
    expect(screen.getByText(/not by the AI/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download test file' })).toBeInTheDocument();
  });

  it('keeps the earlier layout for an investigation without the new fields', () => {
    renderRun(FAILED_RUN, { investigation: INVESTIGATION });
    expect(screen.queryByTestId('row-fixes')).not.toBeInTheDocument();
    expect(screen.queryByTestId('investigation-model')).not.toBeInTheDocument();
    expect(screen.getByText('Recommended fix')).toBeInTheDocument();
  });
});
