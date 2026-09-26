import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UploadPage from './UploadPage';
import { deferred, mockFetch, renderWithMantine } from '../test/utils';

const TARGET = {
  target_id: 'orders', table_name: 'sales_orders', display_name: 'Sales orders',
  description: 'Orders placed through the web shop', database_type: 'sqlite',
};

const RUN = {
  run_id: 'run_0a1b2c3d4e5f', parent_run_id: null, target_id: 'orders', target_table: 'sales_orders',
  file_name: 'orders.csv', status: 'CREATED', created_at: '2026-09-26T10:30:00Z', completed_at: null,
  summary: { rows_received: 3, checks_total: 0, checks_passed: 0, checks_failed: 0 },
  validation_results: [], load_result: null,
};

const csv = (name = 'orders.csv', text = 'order_id,order_ref\n1,A\n2,B\n3,C\n') => new File([text], name, { type: 'text/csv' });

function setup(props = {}) {
  const onCreated = vi.fn();
  const onBack = vi.fn();
  renderWithMantine(<UploadPage target={TARGET} onCreated={onCreated} onBack={onBack} {...props} />);
  return { onCreated, onBack, user: userEvent.setup() };
}

const fileInput = () => screen.getByLabelText('Choose a CSV file');
const createButton = () => screen.getByRole('button', { name: 'Create run' });

describe('UploadPage', () => {
  it('shows the selected target from the API data', () => {
    mockFetch({});
    setup();
    expect(screen.getByText('Sales orders')).toBeInTheDocument();
    expect(screen.getByText('sales_orders')).toBeInTheDocument();
    expect(screen.getByText('SQLite')).toBeInTheDocument();
    expect(screen.getByText(/maximum 10 MB/)).toBeInTheDocument();
  });

  it('lets the user choose one CSV and shows its name and size', async () => {
    mockFetch({});
    const { user } = setup();
    expect(createButton()).toBeDisabled();

    const file = csv();
    await user.upload(fileInput(), file);
    expect(screen.getByTestId('selected-file-name')).toHaveTextContent('orders.csv');
    expect(screen.getByText(`${file.size} B`)).toBeInTheDocument();
    expect(createButton()).toBeEnabled();

    await user.click(screen.getByRole('button', { name: 'Remove file' }));
    expect(screen.queryByTestId('selected-file-name')).not.toBeInTheDocument();
    expect(createButton()).toBeDisabled();
  });

  it('rejects a non-CSV file in the browser without calling the backend', async () => {
    const fetch = mockFetch({});
    const { user } = setup();
    await user.upload(fileInput(), new File(['{}'], 'orders.json', { type: 'application/json' }));

    expect(screen.getByRole('alert')).toHaveTextContent('orders.json is not a CSV file.');
    expect(createButton()).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rejects a file over 10 MB in the browser without calling the backend', async () => {
    const fetch = mockFetch({});
    const { user } = setup();
    await user.upload(fileInput(), new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'big.csv', { type: 'text/csv' }));

    expect(screen.getByRole('alert')).toHaveTextContent('big.csv is 10.0 MB. The maximum is 10.0 MB.');
    expect(createButton()).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('POSTs multipart form data with exactly target_id and one file, then hands back the run', async () => {
    const fetch = mockFetch({ 'POST /api/runs': () => [201, RUN] });
    const { user, onCreated } = setup();
    const file = csv();
    await user.upload(fileInput(), file);
    await user.click(createButton());

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(RUN));
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('http://api.test/api/runs');
    expect(init.method).toBe('POST');
    expect(init.headers).toBeUndefined(); // the browser sets multipart/form-data with its boundary
    expect(init.body).toBeInstanceOf(FormData);
    expect([...init.body.keys()]).toEqual(['target_id', 'file']);
    expect(init.body.get('target_id')).toBe('orders');
    expect(init.body.getAll('file')).toHaveLength(1);
    expect(init.body.get('file').name).toBe('orders.csv');
  });

  it.each([
    ['unsupported_file_type', 422, 'Unsupported file type'],
    ['malformed_csv', 422, 'The CSV could not be read'],
    ['empty_file', 422, 'The file is empty'],
    ['missing_header', 422, 'The CSV has no header row'],
    ['file_too_large', 413, 'The file is too large'],
  ])('shows the structured %s error under the file and allows a retry', async (code, status, title) => {
    let calls = 0;
    mockFetch({
      'POST /api/runs': () => (++calls === 1
        ? [status, { detail: { code, message: `Backend says: ${code}.`, field: 'file' } }]
        : [201, RUN]),
    });
    const { user, onCreated } = setup();
    await user.upload(fileInput(), csv());
    await user.click(createButton());

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(title);
    expect(alert).toHaveTextContent(`Backend says: ${code}.`);
    expect(alert).not.toHaveTextContent('{');

    await user.click(createButton());
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(RUN));
  });

  it('shows target_not_found with a way back to target selection', async () => {
    mockFetch({
      'POST /api/runs': () => [404, { detail: { code: 'target_not_found', message: "Target 'orders' was not found.", field: 'target_id' } }],
    });
    const { user, onBack } = setup();
    await user.upload(fileInput(), csv());
    await user.click(createButton());

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('This target is no longer available');
    expect(alert).toHaveTextContent("Target 'orders' was not found.");
    await user.click(within(alert).getByRole('button', { name: 'Choose another target' }));
    expect(onBack).toHaveBeenCalled();
  });

  it('shows a network error cleanly', async () => {
    mockFetch({ 'POST /api/runs': () => { throw new TypeError('Failed to fetch'); } });
    const { user } = setup();
    await user.upload(fileInput(), csv());
    await user.click(createButton());

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not reach the backend');
    expect(alert).toHaveTextContent('Could not reach the backend at http://api.test');
    expect(createButton()).toBeEnabled();
  });

  it('shows an unexpected server error without raw bodies', async () => {
    mockFetch({ 'POST /api/runs': () => new Response('Traceback (most recent call last): boom', { status: 500 }) });
    const { user } = setup();
    await user.upload(fileInput(), csv());
    await user.click(createButton());

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The run could not be created');
    expect(alert).toHaveTextContent('Request failed (500).');
    expect(alert).not.toHaveTextContent('Traceback');
  });

  it('prevents a duplicate submit while the request is in progress', async () => {
    const pending = deferred();
    const fetch = mockFetch({ 'POST /api/runs': () => pending.promise });
    const { user, onCreated } = setup();
    await user.upload(fileInput(), csv());

    const button = createButton();
    await user.click(button);
    await user.click(button);
    await user.dblClick(button);

    expect(await screen.findByText('Uploading orders.csv and creating the run…')).toBeInTheDocument();
    expect(button).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Remove file' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
    expect(fetch).toHaveBeenCalledTimes(1);

    pending.resolve([201, RUN]);
    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
