import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RunResultPage from './RunResultPage';
import { renderWithMantine } from '../test/utils';

// Invented target and checks: nothing here exists in the demo, so passing tests prove the UI is generic.
const TARGET = { target_id: 'ledger', table_name: 'ledger_entries', display_name: 'Ledger entries', database_type: 'sqlite' };

const RESULTS = [
  { name: 'required_columns', status: 'PASSED', severity: 'INFO', summary: 'All required columns are present.', metrics: {}, evidence: [] },
  { name: 'amount_limit', status: 'FAILED', severity: 'ERROR', summary: 'Amounts above the configured limit were found.',
    metrics: { affected_rows: 1, limit: 50000 }, evidence: ['[validation.amount_limit.001] amount=999999 exceeds configured limit'] },
  { name: 'currency_code.allowed', status: 'FAILED', severity: 'ERROR', summary: 'Unknown currency codes.',
    metrics: { affected_rows: 2, invalid_values: { XYZ: 1, 'eur ': 1 } },
    evidence: ['row 3: currency_code="XYZ" is not allowed', 'row 9: currency_code="eur " is not allowed', '... and 0 more'] },
  { name: 'unexpected_columns', status: 'WARNING', severity: 'WARNING', summary: 'Column memo is not in the target and will be ignored.',
    metrics: { columns: 1 }, evidence: ['memo'] },
  { name: 'foreign_key.account_id', status: 'SKIPPED', severity: 'INFO', summary: 'Referenced table not available.', metrics: {}, evidence: [] },
  { name: 'not_null.entry_id', status: 'PASSED', severity: 'INFO', summary: 'No null entry_id values.', metrics: {}, evidence: [] },
  { name: 'data_type.posted_on', status: 'PASSED', severity: 'INFO', summary: 'posted_on values are compatible.', metrics: {}, evidence: [] },
];

const FAILED_RUN = {
  run_id: 'run_ab12cd34ef56', parent_run_id: null, target_id: 'ledger', target_table: 'ledger_entries',
  file_name: 'ledger_2026-09.csv', status: 'FAILED_VALIDATION', created_at: '2026-09-26T10:30:00Z',
  completed_at: '2026-09-26T10:30:01Z',
  summary: { rows_received: 1204, checks_total: 7, checks_passed: 3, checks_failed: 2 },
  validation_results: RESULTS, load_result: null,
};

function renderRun(run, props = {}) {
  return renderWithMantine(
    <RunResultPage run={run} target={TARGET} onUploadAnother={vi.fn()} onChooseTarget={vi.fn()} {...props} />,
  );
}

const stat = (label) => screen.getByTestId(`stat-${label.toLowerCase()}`);

describe('RunResultPage', () => {
  it('renders FAILED_VALIDATION as a failure, without any load or success claim', () => {
    renderRun(FAILED_RUN);
    expect(screen.getByRole('heading', { name: 'Validation failed' })).toBeInTheDocument();
    expect(screen.getByTestId('run-status')).toHaveTextContent('FAILED VALIDATION');
    expect(screen.getByTestId('run-id')).toHaveTextContent('run_ab12cd34ef56');
    expect(screen.getByText('Ledger entries')).toBeInTheDocument();
    expect(screen.getByText('ledger_2026-09.csv')).toBeInTheDocument();
    expect(screen.getByText((1204).toLocaleString())).toBeInTheDocument();
    expect(screen.getByText(/Nothing was written to the table/)).toBeInTheDocument();
    expect(screen.queryByText(/loaded successfully|pipeline succeeded|run succeeded/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Ready for validation')).not.toBeInTheDocument();
  });

  it('shows checks, passed and failed from the backend summary, plus warnings and skipped from the results', () => {
    renderRun(FAILED_RUN);
    expect(stat('Checks')).toHaveTextContent('7');
    expect(stat('Passed')).toHaveTextContent('3');
    expect(stat('Failed')).toHaveTextContent('2');
    expect(stat('Warnings')).toHaveTextContent('1');
    expect(stat('Skipped')).toHaveTextContent('1');
  });

  it('uses the backend summary numbers rather than recounting them', () => {
    renderRun({ ...FAILED_RUN, summary: { rows_received: 10, checks_total: 12, checks_passed: 4, checks_failed: 8 } });
    expect(stat('Checks')).toHaveTextContent('12');
    expect(stat('Passed')).toHaveTextContent('4');
    expect(stat('Failed')).toHaveTextContent('8');
  });

  it('hides the warning and skipped counters when there are none', () => {
    renderRun({ ...FAILED_RUN, validation_results: RESULTS.filter((r) => r.status === 'PASSED' || r.status === 'FAILED') });
    expect(screen.queryByTestId('stat-warnings')).not.toBeInTheDocument();
    expect(screen.queryByTestId('stat-skipped')).not.toBeInTheDocument();
  });

  it('renders every validation result returned, failed first', () => {
    renderRun(FAILED_RUN);
    const items = screen.getAllByTestId('validation-result');
    expect(items).toHaveLength(RESULTS.length);
    expect(items.map((i) => i.dataset.status)).toEqual(['FAILED', 'FAILED', 'WARNING', 'SKIPPED', 'PASSED', 'PASSED', 'PASSED']);
    for (const r of RESULTS) expect(screen.getByText(r.name)).toBeInTheDocument();
  });

  it.each([
    ['PASSED', 'required_columns', 'All required columns are present.', 'INFO'],
    ['FAILED', 'amount_limit', 'Amounts above the configured limit were found.', 'ERROR'],
    ['WARNING', 'unexpected_columns', 'Column memo is not in the target and will be ignored.', 'WARNING'],
    ['SKIPPED', 'foreign_key.account_id', 'Referenced table not available.', 'INFO'],
  ])('renders a %s result with its name, status, severity and message', (status, name, message, severity) => {
    renderRun(FAILED_RUN);
    const item = screen.getAllByTestId('validation-result').find((el) => within(el).queryByText(name));
    expect(item.dataset.status).toBe(status);
    expect(within(item).getAllByText(status).length).toBeGreaterThan(0);
    expect(within(item).getByText(message)).toBeInTheDocument();
    expect(within(item).getAllByText(severity).length).toBeGreaterThan(0);
  });

  it('shows evidence exactly as the backend returned it', () => {
    renderRun(FAILED_RUN);
    const item = screen.getAllByTestId('validation-result').find((el) => within(el).queryByText('currency_code.allowed'));
    const evidence = within(item).getByRole('list', { name: 'Evidence' });
    expect(within(evidence).getAllByRole('listitem').map((li) => li.textContent)).toEqual(RESULTS[2].evidence);
    // Metrics are shown as returned, including value -> count maps.
    expect(within(item).getByText('Invalid values')).toBeInTheDocument();
    expect(within(item).getByText('XYZ × 1')).toBeInTheDocument();
  });

  it('renders an invented check (amount_limit) with no special-case code', () => {
    renderRun({
      ...FAILED_RUN,
      summary: { rows_received: 1, checks_total: 1, checks_passed: 0, checks_failed: 1 },
      validation_results: [RESULTS[1]],
    });
    const item = screen.getByTestId('validation-result');
    expect(within(item).getByText('Amount limit')).toBeInTheDocument();
    expect(within(item).getByText('amount_limit')).toBeInTheDocument();
    expect(within(item).getByText('[validation.amount_limit.001] amount=999999 exceeds configured limit')).toBeInTheDocument();
    expect(within(item).getByText('50000')).toBeInTheDocument();
  });

  it('still renders a CREATED run as in Milestone 2', () => {
    renderRun({ ...FAILED_RUN, status: 'CREATED', validation_results: [],
      summary: { rows_received: 3, checks_total: 0, checks_passed: 0, checks_failed: 0 } });
    expect(screen.getByRole('heading', { name: 'Run created' })).toBeInTheDocument();
    expect(screen.getByText('Ready for validation')).toBeInTheDocument();
    expect(screen.getByTestId('run-status')).toHaveTextContent('CREATED');
    expect(screen.queryByRole('heading', { name: 'Validation' })).not.toBeInTheDocument();
  });

  it('words a passing run by its status, never as loaded unless the backend says so', () => {
    renderRun({ ...FAILED_RUN, status: 'LOADING',
      summary: { rows_received: 1204, checks_total: 3, checks_passed: 3, checks_failed: 0 },
      validation_results: RESULTS.filter((r) => r.status === 'PASSED') });
    expect(screen.getByRole('heading', { name: 'Validation passed' })).toBeInTheDocument();
    expect(screen.getByText(/has not completed/)).toBeInTheDocument();
    expect(screen.queryByText(/loaded successfully/i)).not.toBeInTheDocument();
    expect(stat('Failed')).toHaveTextContent('0');
  });

  it('shows an unknown status as returned', () => {
    renderRun({ ...FAILED_RUN, status: 'QUEUED' });
    expect(screen.getByTestId('run-status')).toHaveTextContent('QUEUED');
    expect(screen.getByRole('heading', { name: 'Run queued' })).toBeInTheDocument();
  });

  it('keeps the navigation actions', async () => {
    const onUploadAnother = vi.fn();
    const onChooseTarget = vi.fn();
    renderRun(FAILED_RUN, { onUploadAnother, onChooseTarget });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Upload another file' }));
    await user.click(screen.getByRole('button', { name: 'Choose another target' }));
    expect(onUploadAnother).toHaveBeenCalled();
    expect(onChooseTarget).toHaveBeenCalled();
  });
});
