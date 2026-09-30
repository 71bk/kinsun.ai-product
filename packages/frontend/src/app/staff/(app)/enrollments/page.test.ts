// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement, StrictMode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import * as api from '@/lib/api/elder-enrollments';
import { getRuntimeConfig } from '@/lib/runtime-config';
import EnrollmentsPage from './page';

vi.mock('@/lib/api/elder-enrollments');
vi.mock('@/lib/runtime-config');
const record: api.Enrollment = {
  enrollment_id: 'enrollment', elder_id: 'elder', display_name: 'Synthetic elder',
  care_unit_id: 'unit', status: 'SUSPENDED', version: 2, can_manage: true,
  valid_from: '2026-09-29T01:00:00Z', valid_until: null, ended_at: null,
};
function setup() {
  return render(createElement(StrictMode, { children: createElement(LocaleProvider, {
    initialLocale: 'en', children: createElement(EnrollmentsPage),
  }) }));
}
beforeEach(() => {
  vi.mocked(getRuntimeConfig).mockResolvedValue({ apiBaseUrl: '/backend/core', elderId: '',
    caregiverId: '', consentPolicyVersion: '', credentialStatus: 'present' });
  vi.mocked(api.listEnrollments).mockResolvedValue({ items: [record], has_more: false, next_cursor: null });
  vi.mocked(api.getEnrollment).mockResolvedValue(record);
  vi.mocked(api.listEnrollmentHistory).mockResolvedValue({ items: [], has_more: false, next_cursor: null });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('loads under StrictMode and reaches suspended recovery without care access', async () => {
  setup();
  fireEvent.click(await screen.findByRole('button', { name: 'Synthetic elder Suspended' }));
  await screen.findByRole('button', { name: 'Resume service' });
  expect(screen.queryByRole('link', { name: 'Open elder profile' })).toBeNull();
});

it('appends the next page without clearing the current selection', async () => {
  vi.mocked(api.listEnrollments).mockResolvedValueOnce({ items: [record], has_more: true, next_cursor: 'page-two' });
  setup();
  fireEvent.click(await screen.findByRole('button', { name: 'Synthetic elder Suspended' }));
  await screen.findByRole('button', { name: 'Resume service' });
  vi.mocked(api.listEnrollments).mockResolvedValue({ items: [{ ...record, enrollment_id: 'ended', display_name: 'Second elder', status: 'ENDED' }], has_more: false, next_cursor: null });
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }));
  await screen.findByRole('button', { name: 'Second elder Ended' });
  await waitFor(() => expect(api.listEnrollments).toHaveBeenCalledWith({ apiBaseUrl: '/backend/core' }, 'page-two'));
  expect(screen.getByRole('button', { name: 'Resume service' })).toBeTruthy();
});

it('renders an empty result', async () => {
  vi.mocked(api.listEnrollments).mockResolvedValue({ items: [], has_more: false, next_cursor: null });
  setup(); await screen.findByText('No enrollments are available to manage.');
});
