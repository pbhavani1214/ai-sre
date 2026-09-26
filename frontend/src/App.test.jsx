import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { mockFetch, renderWithMantine } from './test/utils';

const DATABASES = {
  databases: [{ database_id: 'shop', display_name: 'Web shop', file_name: 'shop.db', database_type: 'sqlite', table_count: 1, is_default: true }],
};
const TARGETS = {
  targets: [{ target_id: 'orders', table_name: 'sales_orders', display_name: 'Sales orders', description: 'Web shop orders', database_type: 'sqlite' }],
};
const DETAIL = {
  target_id: 'orders', table_name: 'sales_orders', database_type: 'sqlite',
  columns: [{ name: 'order_id', data_type: 'INTEGER', nullable: false, primary_key: true, unique: false }],
  constraints: [{ type: 'PRIMARY_KEY', columns: ['order_id'], description: 'order_id must be unique and non-null' }],
};
const RUN = {
  run_id: 'run_9f8e7d6c5b4a', parent_run_id: null, database_id: 'shop', target_id: 'orders', target_table: 'sales_orders',
  file_name: 'orders_2026-09-26.csv', status: 'CREATED', created_at: '2026-09-26T10:30:00Z', completed_at: null,
  summary: { rows_received: 1250, checks_total: 0, checks_passed: 0, checks_failed: 0 },
  validation_results: [], load_result: null,
};

describe('live flow: target selection -> upload -> run created', () => {
  it('walks from target selection to a created run', async () => {
    const fetch = mockFetch({
      'GET /health': () => [200, { status: 'ok', llm_configured: true, details: {} }],
      'GET /api/databases': () => [200, DATABASES],
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, DETAIL],
      'POST /api/runs': () => [201, RUN],
    });
    renderWithMantine(<App />);
    const user = userEvent.setup();

    // 1. Target selection
    await user.click(await screen.findByRole('combobox', { name: 'Database' }));
    await user.click(await screen.findByRole('option', { name: 'Web shop (shop.db) · default' }));
    await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
    await user.click(await screen.findByRole('option', { name: 'Sales orders' }));
    const continueButton = screen.getByRole('button', { name: 'Continue' });
    await waitFor(() => expect(continueButton).toBeEnabled());
    await user.click(continueButton);

    // 2. Upload
    expect(await screen.findByRole('heading', { name: 'Upload a CSV' })).toBeInTheDocument();
    expect(screen.getByText('sales_orders')).toBeInTheDocument();
    await user.upload(screen.getByLabelText('Choose a CSV file'), new File(['order_id\n1\n'], 'orders_2026-09-26.csv', { type: 'text/csv' }));
    await user.click(screen.getByRole('button', { name: 'Create run' }));

    // 3. Run created: only what the backend returned, no validation/load/AI claims
    expect(await screen.findByRole('heading', { name: 'Run created' })).toBeInTheDocument();
    const post = fetch.mock.calls.find(([u, i]) => u.endsWith('/api/runs') && i?.method === 'POST');
    expect([...post[1].body.keys()]).toEqual(['target_id', 'file', 'database_id']);
    expect(post[1].body.get('database_id')).toBe('shop');
    expect(screen.getByTestId('run-database')).toHaveTextContent('in Web shop (shop.db)');
    expect(screen.getByTestId('run-id')).toHaveTextContent('run_9f8e7d6c5b4a');
    expect(screen.getByTestId('run-status')).toHaveTextContent('CREATED');
    expect(screen.getByText('Sales orders')).toBeInTheDocument();
    expect(screen.getByText('orders_2026-09-26.csv')).toBeInTheDocument();
    expect(screen.getByText((1250).toLocaleString())).toBeInTheDocument();
    expect(screen.getByText('Ready for validation')).toBeInTheDocument();
    expect(screen.queryByText(/validation passed|loaded successfully|root cause/i)).not.toBeInTheDocument();

    // Back to upload keeps the target; back to targets keeps the selection
    await user.click(screen.getByRole('button', { name: 'Upload another file' }));
    expect(await screen.findByRole('heading', { name: 'Upload a CSV' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByRole('combobox', { name: 'Database' })).toHaveValue('Web shop (shop.db) · default');
    expect(await screen.findByRole('combobox', { name: 'Target table' })).toHaveValue('Sales orders');
  });

  it('shows any non-CREATED status as returned, without claiming success', async () => {
    mockFetch({
      'GET /health': () => [200, { status: 'ok', llm_configured: true, details: {} }],
      'GET /api/databases': () => [200, DATABASES],
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, DETAIL],
      'POST /api/runs': () => [201, { ...RUN, status: 'FAILED_VALIDATION' }],
    });
    renderWithMantine(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('combobox', { name: 'Database' }));
    await user.click(await screen.findByRole('option', { name: 'Web shop (shop.db) · default' }));
    await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
    await user.click(await screen.findByRole('option', { name: 'Sales orders' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.upload(await screen.findByLabelText('Choose a CSV file'), new File(['order_id\n1\n'], 'o.csv', { type: 'text/csv' }));
    await user.click(screen.getByRole('button', { name: 'Create run' }));

    expect(await screen.findByTestId('run-status')).toHaveTextContent('FAILED VALIDATION');
    expect(screen.queryByText('Ready for validation')).not.toBeInTheDocument();
  });

  it('full live flow: failed validation -> investigate -> corrected retry -> SUCCEEDED, parent kept unchanged', async () => {
    const FAILED = { ...RUN, status: 'FAILED_VALIDATION', completed_at: '2026-09-26T10:30:01Z',
      summary: { rows_received: 7, checks_total: 2, checks_passed: 1, checks_failed: 1 },
      validation_results: [
        { name: 'primary_key_uniqueness', status: 'FAILED', severity: 'ERROR', summary: 'Duplicate keys.', metrics: { affected_rows: 2 },
          evidence: ["[validation.primary_key_uniqueness.001] order_id='7' appears 2 times (rows 2, 3)"] },
        { name: 'required_columns', status: 'PASSED', severity: 'INFO', summary: 'All present.', metrics: {}, evidence: [] },
      ] };
    const INVESTIGATION = {
      run_id: FAILED.run_id, summary: 'Duplicate order ids in the export.', observed_facts: ['[validation.primary_key_uniqueness] order_id 7 twice'],
      hypotheses: [{ hypothesis: 'The export repeats a batch.', status: 'SUPPORTED', evidence: [], reasoning: 'Two identical ids.' }],
      root_cause_status: 'IDENTIFIED', root_cause: 'Batch repeated in export.', root_cause_evidence: [], root_cause_reasoning: 'Ids repeat.',
      recommended_fix: 'Remove the duplicate row and retry.', regression_test: 'assert ids.is_unique', investigation_trace: [], evidence_warnings: [],
    };
    const CHILD = { ...RUN, run_id: 'run_111111111111', parent_run_id: FAILED.run_id, file_name: 'orders_fixed.csv', status: 'SUCCEEDED',
      completed_at: '2026-09-26T10:35:01Z', summary: { rows_received: 6, checks_total: 2, checks_passed: 2, checks_failed: 0 },
      validation_results: [], load_result: { rows_loaded: 6, target_table: 'sales_orders' } };
    const fetch = mockFetch({
      'GET /health': () => [200, { status: 'ok', llm_configured: true, details: {} }],
      'GET /api/databases': () => [200, DATABASES],
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, DETAIL],
      'POST /api/runs': () => [201, FAILED],
      [`POST /api/runs/${FAILED.run_id}/investigate`]: () => [200, INVESTIGATION],
      [`POST /api/runs/${FAILED.run_id}/retry`]: () => [201, CHILD],
    });
    renderWithMantine(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('combobox', { name: 'Database' }));
    await user.click(await screen.findByRole('option', { name: 'Web shop (shop.db) · default' }));
    await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
    await user.click(await screen.findByRole('option', { name: 'Sales orders' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.upload(await screen.findByLabelText('Choose a CSV file'), new File(['order_id\n7\n7\n'], 'orders.csv', { type: 'text/csv' }));
    await user.click(screen.getByRole('button', { name: 'Create run' }));

    expect(await screen.findByRole('heading', { name: 'Validation failed' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Investigate with AI' }));
    expect(await screen.findByText('Batch repeated in export.')).toBeInTheDocument();
    expect(screen.getByText('Remove the duplicate row and retry.')).toBeInTheDocument();

    const retry = screen.getByTestId('retry-panel');
    await user.upload(within(retry).getByLabelText('Choose a CSV file'), new File(['order_id\n7\n'], 'orders_fixed.csv', { type: 'text/csv' }));
    await user.click(within(retry).getByRole('button', { name: 'Retry with corrected file' }));

    expect(await screen.findByRole('heading', { name: 'Loaded successfully' })).toBeInTheDocument();
    expect(screen.getByTestId('run-id')).toHaveTextContent('run_111111111111');
    expect(screen.getByTestId('parent-link')).toHaveTextContent(FAILED.run_id);
    expect(screen.getByTestId('load-rows_loaded')).toHaveTextContent('6');

    // The original run is unchanged, and its investigation is still there.
    await user.click(screen.getByRole('button', { name: 'View original run' }));
    expect(await screen.findByRole('heading', { name: 'Validation failed' })).toBeInTheDocument();
    expect(screen.getByTestId('run-id')).toHaveTextContent(FAILED.run_id);
    expect(screen.getByText('Batch repeated in export.')).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([u]) => u.endsWith('/investigate'))).toHaveLength(1);
  });

  it('a retry that fails validation shows the new failed run, which can be investigated on its own', async () => {
    const FAILED = { ...RUN, status: 'FAILED_VALIDATION', validation_results: [],
      summary: { rows_received: 3, checks_total: 1, checks_passed: 0, checks_failed: 1 } };
    const CHILD = { ...FAILED, run_id: 'run_222222222222', parent_run_id: FAILED.run_id, file_name: 'still_bad.csv' };
    const fetch = mockFetch({
      'GET /health': () => [200, { status: 'ok', llm_configured: true, details: {} }],
      'GET /api/databases': () => [200, DATABASES],
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, DETAIL],
      'POST /api/runs': () => [201, FAILED],
      [`POST /api/runs/${FAILED.run_id}/retry`]: () => [201, CHILD],
      [`POST /api/runs/${CHILD.run_id}/investigate`]: () => [503, { detail: { code: 'llm_not_configured', message: 'No API key.', field: null } }],
    });
    renderWithMantine(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('combobox', { name: 'Database' }));
    await user.click(await screen.findByRole('option', { name: 'Web shop (shop.db) · default' }));
    await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
    await user.click(await screen.findByRole('option', { name: 'Sales orders' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.upload(await screen.findByLabelText('Choose a CSV file'), new File(['order_id\n1\n'], 'orders.csv', { type: 'text/csv' }));
    await user.click(screen.getByRole('button', { name: 'Create run' }));
    const retry = await screen.findByTestId('retry-panel');
    await user.upload(within(retry).getByLabelText('Choose a CSV file'), new File(['order_id\n1\n'], 'still_bad.csv', { type: 'text/csv' }));
    await user.click(within(retry).getByRole('button', { name: 'Retry with corrected file' }));

    await waitFor(() => expect(screen.getByTestId('run-id')).toHaveTextContent('run_222222222222'));
    expect(screen.getByRole('heading', { name: 'Validation failed' })).toBeInTheDocument();
    expect(screen.getByTestId('parent-link')).toHaveTextContent(FAILED.run_id);
    await user.click(screen.getByRole('button', { name: 'Investigate with AI' }));
    expect(await screen.findByText('AI investigation is not configured')).toBeInTheDocument();
    expect(fetch.mock.calls.map(([u]) => u).filter((u) => u.includes('/investigate'))).toEqual([`http://api.test/api/runs/${CHILD.run_id}/investigate`]);
  });
});
