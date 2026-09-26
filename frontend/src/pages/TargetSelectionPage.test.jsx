import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TargetSelectionPage from './TargetSelectionPage';
import { deferred, mockFetch, renderWithMantine } from '../test/utils';

// Deliberately not the customer demo: the page must render whatever the API returns.
const TARGETS = {
  targets: [
    { target_id: 'orders', table_name: 'sales_orders', display_name: 'Sales orders',
      description: 'Orders placed through the web shop', database_type: 'sqlite' },
    { target_id: 'products', table_name: 'product_catalog', display_name: 'Product catalog', database_type: 'sqlite' },
  ],
};

const ORDERS_DETAIL = {
  target_id: 'orders',
  table_name: 'sales_orders',
  database_type: 'sqlite',
  columns: [
    { name: 'order_id', data_type: 'INTEGER', nullable: false, primary_key: true, unique: false },
    { name: 'order_ref', data_type: 'TEXT', nullable: false, primary_key: false, unique: true },
    { name: 'channel', data_type: 'TEXT', nullable: true, primary_key: false, unique: false },
    { name: 'note', data_type: 'TEXT', nullable: true, primary_key: false, unique: false },
  ],
  constraints: [
    { type: 'PRIMARY_KEY', columns: ['order_id'], description: 'order_id must be unique and non-null' },
    { type: 'UNIQUE', columns: ['order_ref'], description: 'order_ref must be unique' },
    { type: 'NOT_NULL', columns: ['order_id', 'order_ref'], description: 'Required fields cannot be null' },
    { type: 'CHECK', columns: ['channel'], allowed_values: ['WEB', 'STORE'], description: 'channel must be an allowed value' },
  ],
};

async function chooseTarget(user, label) {
  await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
  await user.click(await screen.findByRole('option', { name: label }));
}

describe('TargetSelectionPage', () => {
  it('shows a loading state, then lists the targets from GET /api/targets', async () => {
    const pending = deferred();
    const fetch = mockFetch({ 'GET /api/targets': () => pending.promise });
    renderWithMantine(<TargetSelectionPage />);

    expect(screen.getByText('Loading targets…')).toBeInTheDocument();
    pending.resolve([200, TARGETS]);

    const user = userEvent.setup();
    await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
    const options = await screen.findAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual(['Sales orders', 'Product catalog']);
    expect(screen.queryByText('Loading targets…')).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/targets', expect.anything());
  });

  it('shows the selected target summary using the API fields', async () => {
    mockFetch({
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, ORDERS_DETAIL],
    });
    renderWithMantine(<TargetSelectionPage />);
    await chooseTarget(userEvent.setup(), 'Sales orders');

    expect(screen.getAllByText('Sales orders').length).toBeGreaterThan(0);
    expect(screen.getAllByText('sales_orders').length).toBeGreaterThan(0);
    expect(screen.getByText('SQLite')).toBeInTheDocument();
    expect(screen.getByText('Orders placed through the web shop')).toBeInTheDocument();
  });

  it('loads the schema with GET /api/targets/{target_id} after selection, showing a loading state', async () => {
    const pending = deferred();
    const fetch = mockFetch({
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => pending.promise,
    });
    renderWithMantine(<TargetSelectionPage />);
    await chooseTarget(userEvent.setup(), 'Sales orders');

    expect(await screen.findByText('Loading target schema…')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/targets/orders', expect.anything());
    pending.resolve([200, ORDERS_DETAIL]);
    expect(await screen.findByRole('table', { name: 'Target columns' })).toBeInTheDocument();
    expect(screen.queryByText('Loading target schema…')).not.toBeInTheDocument();
  });

  it('renders columns and constraints from the schema response', async () => {
    mockFetch({
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, ORDERS_DETAIL],
    });
    renderWithMantine(<TargetSelectionPage />);
    await chooseTarget(userEvent.setup(), 'Sales orders');

    const table = await screen.findByRole('table', { name: 'Target columns' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows.map((r) => within(r).getAllByRole('cell')[0].textContent)).toEqual(['order_id', 'order_ref', 'channel', 'note']);

    const [idRow, refRow, channelRow, noteRow] = rows;
    expect(idRow).toHaveTextContent('INTEGER');
    expect(within(idRow).getByText('Primary key')).toBeInTheDocument();
    expect(within(idRow).getByText('Required')).toBeInTheDocument();
    expect(within(refRow).getByText('Unique')).toBeInTheDocument();
    expect(within(channelRow).getByText('Check')).toBeInTheDocument();
    expect(within(noteRow).getByText('Optional')).toBeInTheDocument();

    expect(screen.getByText('order_ref must be unique')).toBeInTheDocument();
    expect(screen.getByText('channel must be an allowed value')).toBeInTheDocument();
    expect(screen.getByText('WEB')).toBeInTheDocument();
    expect(screen.getByText('STORE')).toBeInTheDocument();
    expect(screen.getByText('Not null')).toBeInTheDocument();
  });

  it('shows a friendly error and retries when GET /api/targets fails', async () => {
    let calls = 0;
    mockFetch({
      'GET /api/targets': () => (++calls === 1
        ? [500, { detail: { code: 'internal_error', message: 'The target database could not be opened.', field: null } }]
        : [200, TARGETS]),
    });
    renderWithMantine(<TargetSelectionPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load the target tables');
    expect(alert).toHaveTextContent('The target database could not be opened.');
    expect(alert).not.toHaveTextContent('Traceback');

    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('combobox', { name: 'Target table' })).toBeInTheDocument();
  });

  it('shows a network error without falling back to any bundled data', async () => {
    mockFetch({ 'GET /api/targets': () => { throw new TypeError('Failed to fetch'); } });
    renderWithMantine(<TargetSelectionPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend at http://api.test');
    expect(screen.queryByRole('combobox', { name: 'Target table' })).not.toBeInTheDocument();
  });

  it('handles 404 target_not_found for the selected target', async () => {
    mockFetch({
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [404, { detail: { code: 'target_not_found', message: "Target 'orders' was not found.", field: 'target_id' } }],
    });
    renderWithMantine(<TargetSelectionPage />);
    await chooseTarget(userEvent.setup(), 'Sales orders');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('This target is no longer available');
    expect(alert).toHaveTextContent("Target 'orders' was not found.");
    expect(within(alert).getByRole('button', { name: 'Reload targets' })).toBeInTheDocument();
  });

  it('shows the latest selection only, even if an earlier schema request finishes last', async () => {
    const slowOrders = deferred();
    mockFetch({
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => slowOrders.promise,
      'GET /api/targets/products': () => [200, {
        target_id: 'products', table_name: 'product_catalog', database_type: 'sqlite',
        columns: [{ name: 'sku', data_type: 'TEXT', nullable: false, primary_key: true, unique: false }],
        constraints: [],
      }],
    });
    renderWithMantine(<TargetSelectionPage />);
    const user = userEvent.setup();
    await chooseTarget(user, 'Sales orders');
    await chooseTarget(user, 'Product catalog');
    expect(await screen.findByText('sku')).toBeInTheDocument();

    slowOrders.resolve([200, ORDERS_DETAIL]);
    await waitFor(() => expect(screen.queryByText('order_id')).not.toBeInTheDocument());
    expect(screen.getByText('This table declares no constraints.')).toBeInTheDocument();
  });

  it('keeps Continue disabled until a target is selected, and has no demo link', async () => {
    mockFetch({ 'GET /api/targets': () => [200, TARGETS] });
    renderWithMantine(<TargetSelectionPage onContinue={vi.fn()} />);

    expect(await screen.findByRole('button', { name: 'Continue' })).toBeDisabled();
    expect(screen.queryByText(/try the demo/i)).not.toBeInTheDocument();
  });

  it('enables Continue only after the selected target schema has loaded, then continues with that target', async () => {
    const pending = deferred();
    mockFetch({
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => pending.promise,
    });
    const onContinue = vi.fn();
    renderWithMantine(<TargetSelectionPage onContinue={onContinue} />);
    const user = userEvent.setup();
    await chooseTarget(user, 'Sales orders');

    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled(); // schema still loading
    pending.resolve([200, ORDERS_DETAIL]);
    const button = await screen.findByRole('button', { name: 'Continue' });
    await waitFor(() => expect(button).toBeEnabled());

    await user.click(button);
    expect(onContinue).toHaveBeenCalledWith(TARGETS.targets[0]);
  });

  it('keeps Continue disabled when the schema fails to load', async () => {
    mockFetch({
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [500, { detail: { code: 'internal_error', message: 'Could not read the schema.', field: null } }],
    });
    renderWithMantine(<TargetSelectionPage onContinue={vi.fn()} />);
    await chooseTarget(userEvent.setup(), 'Sales orders');

    await screen.findByText('Could not read the schema.');
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });
});
