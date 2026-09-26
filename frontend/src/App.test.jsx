import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { mockFetch, renderWithMantine } from './test/utils';

const TARGETS = {
  targets: [{ target_id: 'orders', table_name: 'sales_orders', display_name: 'Sales orders', description: 'Web shop orders', database_type: 'sqlite' }],
};
const DETAIL = {
  target_id: 'orders', table_name: 'sales_orders', database_type: 'sqlite',
  columns: [{ name: 'order_id', data_type: 'INTEGER', nullable: false, primary_key: true, unique: false }],
  constraints: [{ type: 'PRIMARY_KEY', columns: ['order_id'], description: 'order_id must be unique and non-null' }],
};
const RUN = {
  run_id: 'run_9f8e7d6c5b4a', parent_run_id: null, target_id: 'orders', target_table: 'sales_orders',
  file_name: 'orders_2026-09-26.csv', status: 'CREATED', created_at: '2026-09-26T10:30:00Z', completed_at: null,
  summary: { rows_received: 1250, checks_total: 0, checks_passed: 0, checks_failed: 0 },
  validation_results: [], load_result: null,
};

describe('live flow: target selection -> upload -> run created', () => {
  it('walks from target selection to a created run', async () => {
    mockFetch({
      'GET /health': () => [200, { status: 'ok', llm_configured: true, details: {} }],
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, DETAIL],
      'POST /api/runs': () => [201, RUN],
    });
    renderWithMantine(<App />);
    const user = userEvent.setup();

    // 1. Target selection
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
    expect(await screen.findByRole('combobox', { name: 'Target table' })).toHaveValue('Sales orders');
  });

  it('shows any non-CREATED status as returned, without claiming success', async () => {
    mockFetch({
      'GET /health': () => [200, { status: 'ok', llm_configured: true, details: {} }],
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, DETAIL],
      'POST /api/runs': () => [201, { ...RUN, status: 'FAILED_VALIDATION' }],
    });
    renderWithMantine(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
    await user.click(await screen.findByRole('option', { name: 'Sales orders' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.upload(await screen.findByLabelText('Choose a CSV file'), new File(['order_id\n1\n'], 'o.csv', { type: 'text/csv' }));
    await user.click(screen.getByRole('button', { name: 'Create run' }));

    expect(await screen.findByTestId('run-status')).toHaveTextContent('FAILED VALIDATION');
    expect(screen.queryByText('Ready for validation')).not.toBeInTheDocument();
  });
});
