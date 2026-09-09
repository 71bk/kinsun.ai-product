// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { completeAssignment, listAssignments, type AssignmentView } from '@/lib/api/assignments';
import { ApiRequestError } from '@/lib/api/client';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { getRuntimeConfig } from '@/lib/runtime-config';
import AssignmentsPage from './page';

vi.mock('@/lib/runtime-config', () => ({ getRuntimeConfig: vi.fn() }));
vi.mock('@/lib/api/assignments', () => ({
  listAssignments: vi.fn(),
  completeAssignment: vi.fn(),
  startAssignment: vi.fn(),
}));
const list = vi.mocked(listAssignments);
const complete = vi.mocked(completeAssignment);
const visit: AssignmentView = {
  assignmentId: 'visit',
  elderId: 'elder',
  scheduledStart: new Date(Date.now() - 1000).toISOString(),
  scheduledEnd: new Date(Date.now() + 3600000).toISOString(),
  expiresAt: new Date(Date.now() + 3600000).toISOString(),
  status: 'IN_PROGRESS',
  version: 2,
  scopeCount: 1,
};
function mount() {
  return render(
    createElement(LocaleProvider, {
      initialLocale: 'en',
      children: createElement(AssignmentsPage),
    }),
  );
}
beforeEach(() => {
  vi.mocked(getRuntimeConfig).mockResolvedValue({
    apiBaseUrl: '/backend/core',
    credentialStatus: 'present',
    elderId: '',
    caregiverId: '',
    consentPolicyVersion: '',
  });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
});

it('ignores a late list response after the selected date changes', async () => {
  let resolve!: (value: AssignmentView[]) => void;
  list
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockResolvedValue([]);
  const view = mount();
  await screen.findByLabelText('Assignment date');
  fireEvent.change(view.container.querySelector('input[type="date"]')!, {
    target: { value: '2026-09-08' },
  });
  await screen.findByText('No assignments that day');
  await act(async () => resolve([visit]));
  expect(screen.queryByRole('button', { name: 'Complete service' })).toBeNull();
});

it('clears visible assignments on hide and only accepts the new visible-page response', async () => {
  let resolve!: (value: AssignmentView[]) => void;
  list.mockResolvedValueOnce([visit]).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  mount();
  await screen.findByRole('button', { name: 'Complete service' });
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  fireEvent(document, new Event('visibilitychange'));
  expect(screen.queryByRole('button', { name: 'Complete service' })).toBeNull();
  hidden.mockReturnValue(false);
  fireEvent(document, new Event('visibilitychange'));
  await act(async () => resolve([]));
  await screen.findByText('No assignments that day');
});

it('does not restore an assignment from a command completed after focus revalidation', async () => {
  let resolve!: (value: AssignmentView) => void;
  list.mockResolvedValueOnce([visit]).mockResolvedValue([]);
  complete.mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Complete service' }));
  const buttons = await screen.findAllByRole('button', { name: 'Complete service' });
  fireEvent.click(buttons[buttons.length - 1]);
  fireEvent(window, new Event('focus'));
  await screen.findByText('No assignments that day');
  await act(async () => resolve({ ...visit, status: 'COMPLETED', version: 3 }));
  expect(screen.queryByText('Version 3')).toBeNull();
  expect(screen.queryByRole('article')).toBeNull();
});

it('unmounts all assignment commands after a denied completion', async () => {
  list.mockResolvedValue([visit]);
  complete.mockRejectedValue(new ApiRequestError(403, 'Denied'));
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Complete service' }));
  const buttons = await screen.findAllByRole('button', { name: 'Complete service' });
  fireEvent.click(buttons[buttons.length - 1]);
  await screen.findByText(
    'This account has no home-care assignments it may view, or the assignment has expired.',
  );
  expect(screen.queryByRole('article')).toBeNull();
  expect(complete).toHaveBeenCalledOnce();
});
