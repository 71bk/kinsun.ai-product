// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createElement, StrictMode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ApiRequestError } from '@/lib/api/client';
import * as api from '@/lib/api/elder-enrollments';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { EnrollmentPanel } from './EnrollmentPanel';

vi.mock('@/lib/api/elder-enrollments');
const config = { apiBaseUrl: '/backend/core' };
const lost = vi.fn();
const changed = vi.fn();
const record: api.Enrollment = {
  enrollment_id: 'enrollment', elder_id: 'elder', display_name: 'Synthetic elder',
  care_unit_id: 'unit', status: 'ACTIVE', version: 2, can_manage: true,
  valid_from: '2026-09-29T01:00:00Z', valid_until: null, ended_at: null,
};
function setup() {
  return render(createElement(StrictMode, { children: createElement(LocaleProvider, {
    initialLocale: 'en', children: createElement(EnrollmentPanel, {
      config, enrollmentId: 'enrollment', onAccessLost: lost, onChanged: changed,
    }),
  }) }));
}
async function prepare(action = 'Suspend service', reason = ' Temporary absence ') {
  fireEvent.change(await screen.findByRole('textbox'), { target: { value: reason } });
  fireEvent.click(screen.getByRole('button', { name: action }));
}
function confirm() {
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm' }));
}
beforeEach(() => {
  vi.mocked(api.getEnrollment).mockResolvedValue(record);
  vi.mocked(api.listEnrollmentHistory).mockResolvedValue({ items: [], has_more: false, next_cursor: null });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('requires a reason and confirmation, sends the version, and reads current state after a receipt', async () => {
  setup();
  expect((await screen.findByRole('button', { name: 'Suspend service' }) as HTMLButtonElement).disabled).toBe(true);
  await prepare();
  expect(api.changeEnrollment).not.toHaveBeenCalled();
  expect(within(screen.getByRole('dialog')).getByText(/Existing tablet sessions will end/)).toBeTruthy();
  vi.mocked(api.changeEnrollment).mockResolvedValue({ ...record, status: 'SUSPENDED', version: 3 });
  // A later command may already have ended it when an older receipt is replayed.
  vi.mocked(api.getEnrollment).mockResolvedValue({ ...record, status: 'ENDED', version: 4 });
  confirm();
  await screen.findByText('Enrollment updated.');
  await screen.findByText(/This enrollment has ended/);
  expect(api.changeEnrollment).toHaveBeenCalledWith(config, 'enrollment', 'suspend',
    { expected_version: 2, reason: 'Temporary absence' }, expect.any(String));
  expect(changed).toHaveBeenCalledWith(expect.objectContaining({ status: 'ENDED', version: 4 }));
  expect(screen.queryByRole('textbox')).toBeNull();
});

it('reuses the idempotency key after uncertain failure', async () => {
  vi.mocked(api.changeEnrollment).mockRejectedValue(new ApiRequestError(503, 'private detail', 'UNAVAILABLE'));
  setup(); await prepare(); confirm();
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', { name: 'Suspend service' })); confirm();
  await waitFor(() => expect(api.changeEnrollment).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.changeEnrollment).mock.calls[0][4]).toBe(vi.mocked(api.changeEnrollment).mock.calls[1][4]);
  expect(screen.queryByText('private detail')).toBeNull();
});

it('preserves a conflicting reason until reload is confirmed', async () => {
  vi.mocked(api.changeEnrollment).mockRejectedValue(new ApiRequestError(409, 'conflict', 'CONFLICT'));
  setup(); await prepare(); confirm();
  await screen.findByRole('alert');
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe(' Temporary absence ');
  expect((screen.getByRole('button', { name: 'Suspend service' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe(' Temporary absence ');
  fireEvent.click(screen.getByRole('button', { name: 'Reload' })); confirm();
  await waitFor(() => expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe(''));
});

it.each([401, 403, 404])('clears all content on access loss (%s)', async (status) => {
  vi.mocked(api.changeEnrollment).mockRejectedValue(new ApiRequestError(status, 'denied', 'NOT_FOUND'));
  setup(); await prepare(); confirm();
  await waitFor(() => expect(lost).toHaveBeenCalledOnce());
  expect(screen.queryByText('Synthetic elder')).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(screen.queryByText('Temporary absence')).toBeNull();
});

it('removes the pending command and draft when manage permission is revoked', async () => {
  setup(); await prepare('End enrollment');
  vi.mocked(api.getEnrollment).mockResolvedValue({ ...record, can_manage: false });
  fireEvent.focus(window);
  await screen.findByText('You can view this enrollment but cannot change it.');
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(api.changeEnrollment).not.toHaveBeenCalled();
});

it('offers resume only for suspended enrollments and explains that old sessions stay invalid', async () => {
  vi.mocked(api.getEnrollment).mockResolvedValue({ ...record, status: 'SUSPENDED' });
  setup(); await prepare('Resume service', 'Returned');
  expect(screen.queryByRole('button', { name: 'Suspend service' })).toBeNull();
  expect(within(screen.getByRole('dialog')).getByText(/Old tablet sessions and cancelled visits will not resume/)).toBeTruthy();
});

it('appends history using the server cursor', async () => {
  vi.mocked(api.listEnrollmentHistory).mockResolvedValueOnce({ items: [], next_cursor: 'ignored-strict-render', has_more: true })
    .mockResolvedValueOnce({ items: [], next_cursor: 'next-page', has_more: true });
  setup();
  fireEvent.click(await screen.findByRole('button', { name: 'Load more' }));
  await waitFor(() => expect(api.listEnrollmentHistory).toHaveBeenCalledWith(config, 'enrollment', 'next-page'));
});
