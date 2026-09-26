import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TargetSelectionPage from './TargetSelectionPage';
import { deferred, mockFetch as mockRoutes, renderWithMantine } from '../test/utils';

// Deliberately not the customer demo: the page must render whatever the API returns.
const DATABASES = {
  databases: [
    { database_id: 'shop', display_name: 'Web shop', file_name: 'shop.db', database_type: 'sqlite', table_count: 2, is_default: true },
    { database_id: 'archive', display_name: 'Archive', file_name: 'archive.sqlite', database_type: 'sqlite', table_count: 0, is_default: false },
  ],
};
const SHOP = 'Web shop (shop.db) · default';

/** Every test lists the databases unless it overrides that route. */
const mockFetch = (routes) => mockRoutes({ 'GET /api/databases': () => [200, DATABASES], ...routes });

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

async function chooseDatabase(user, label = SHOP) {
  await user.click(await screen.findByRole('combobox', { name: 'Database' }));
  await user.click(await screen.findByRole('option', { name: label }));
}

async function chooseTarget(user, label) {
  if (!screen.queryByRole('combobox', { name: 'Target table' })) await chooseDatabase(user);
  await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
  await user.click(await screen.findByRole('option', { name: label }));
}

describe('TargetSelectionPage', () => {
  it('lists the databases, then the tables of the chosen database, with loading states', async () => {
    const dbs = deferred();
    const tables = deferred();
    const fetch = mockFetch({ 'GET /api/databases': () => dbs.promise, 'GET /api/targets': () => tables.promise });
    renderWithMantine(<TargetSelectionPage />);
    const user = userEvent.setup();

    expect(screen.getByText('Loading databases…')).toBeInTheDocument();
    dbs.resolve([200, DATABASES]);
    await user.click(await screen.findByRole('combobox', { name: 'Database' }));
    expect((await screen.findAllByRole('option')).map((o) => o.textContent))
      .toEqual([SHOP, 'Archive (archive.sqlite)']);
    expect(screen.queryByRole('combobox', { name: 'Target table' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('option', { name: SHOP }));
    expect(await screen.findByText('Loading tables…')).toBeInTheDocument();
    tables.resolve([200, TARGETS]);
    await user.click(await screen.findByRole('combobox', { name: 'Target table' }));
    expect((await screen.findAllByRole('option')).map((o) => o.textContent)).toEqual(['Sales orders', 'Product catalog']);
    expect(screen.getByText('2 tables in Web shop')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/targets?database_id=shop', expect.anything());
  });

  it('changing the database clears the table and loads that database\'s tables', async () => {
    const fetch = mockFetch({
      'GET /api/targets': () => [200, TARGETS],
      'GET /api/targets/orders': () => [200, ORDERS_DETAIL],
    });
    renderWithMantine(<TargetSelectionPage onContinue={vi.fn()} />);
    const user = userEvent.setup();
    await chooseTarget(user, 'Sales orders');
    await screen.findByRole('table', { name: 'Target columns' });

    fetch.mockImplementation(async (url) => new Response(JSON.stringify(
      new URL(url).pathname === '/api/targets' ? { targets: [] } : DATABASES,
    ), { status: 200 }));
    await chooseDatabase(user, 'Archive (archive.sqlite)');
    expect(await screen.findByText('archive.sqlite has no tables to load into.')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Target columns' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/targets?database_id=archive', expect.anything());
  });

  it('shows an error with retry when the databases cannot be listed', async () => {
    mockFetch({ 'GET /api/databases': () => [500, { detail: { code: 'internal_error', message: 'Database folder unreadable.', field: null } }] });
    renderWithMantine(<TargetSelectionPage />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load the databases');
    expect(alert).toHaveTextContent('Database folder unreadable.');
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument();
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
    expect(screen.getByText('Web shop')).toBeInTheDocument();
    expect(screen.getByText('(shop.db)')).toBeInTheDocument();
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
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/targets/orders?database_id=shop', expect.anything());
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
    await chooseDatabase(userEvent.setup());

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load the tables of Web shop');
    expect(alert).toHaveTextContent('The target database could not be opened.');
    expect(alert).not.toHaveTextContent('Traceback');

    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('combobox', { name: 'Target table' })).toBeInTheDocument();
  });

  it('shows a network error without falling back to any bundled data', async () => {
    mockFetch({ 'GET /api/databases': () => { throw new TypeError('Failed to fetch'); } });
    renderWithMantine(<TargetSelectionPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend at http://api.test');
    expect(screen.queryByRole('combobox', { name: 'Database' })).not.toBeInTheDocument();
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
    expect(onContinue).toHaveBeenCalledWith({ database: DATABASES.databases[0], target: TARGETS.targets[0] });
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
