// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {
  getAssignment,
  startAssignment,
  completeAssignment,
  type AssignmentView,
} from '@/lib/api/assignments';
import { ApiRequestError } from '@/lib/api/client';
import { getRuntimeConfig } from '@/lib/runtime-config';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { notifyAssignmentUpdated } from '@/lib/assignment-updates';
import { AssignmentWorkbench } from './AssignmentWorkbench';

vi.mock('@/lib/runtime-config', () => ({ getRuntimeConfig: vi.fn() }));
vi.mock('@/lib/api/assignments', () => ({
  getAssignment: vi.fn(),
  startAssignment: vi.fn(),
  completeAssignment: vi.fn(),
}));
const get = vi.mocked(getAssignment);
function visit(): AssignmentView {
  return {
    assignmentId: 'selected',
    elderId: 'elder',
    status: 'CONFIRMED',
    version: 1,
    scopeCount: 3,
    scheduledStart: new Date(Date.now() - 1000).toISOString(),
    scheduledEnd: new Date(Date.now() + 3600000).toISOString(),
    expiresAt: new Date(Date.now() + 3600000).toISOString(),
    canReadPreviousServiceRecord: true,
    canReadCareActions: true,
  };
}
function element(id = 'selected') {
  return createElement(LocaleProvider, {
    initialLocale: 'en',
    children: createElement(AssignmentWorkbench, { key: id, assignmentId: id }),
  });
}
beforeEach(() => {
  vi.stubGlobal('BroadcastChannel', undefined);
  vi.mocked(getRuntimeConfig).mockResolvedValue({
    apiBaseUrl: '/backend/core',
    credentialStatus: 'present',
    elderId: '',
    caregiverId: '',
    consentPolicyVersion: '',
  });
  get.mockResolvedValue(visit());
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
it('starts only the selected assignment before showing handover and follow-up entry points', async () => {
  vi.mocked(startAssignment).mockResolvedValue({ ...visit(), status: 'IN_PROGRESS', version: 2 });
  render(element());
  fireEvent.click(await screen.findByRole('button', { name: 'Start service' }));
  expect(screen.queryByRole('button', { name: 'View follow-up tasks' })).toBeNull();
  const buttons = screen.getAllByRole('button', { name: 'Start service' });
  fireEvent.click(buttons[buttons.length - 1]);
  await screen.findByRole('button', { name: 'View follow-up tasks' });
  expect(screen.getByRole('button', { name: 'View previous service record' })).toBeDefined();
  expect(vi.mocked(startAssignment).mock.calls[0][1].assignmentId).toBe('selected');
  expect(get).toHaveBeenCalledTimes(1);
});
it('discards late content from another selected visit', async () => {
  let resolve!: (value: AssignmentView) => void;
  get
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockRejectedValue(new ApiRequestError(404, 'Denied'));
  const view = render(element());
  await act(async () => {});
  view.rerender(element('different'));
  await screen.findByRole('alert');
  await act(async () => resolve(visit()));
  expect(screen.queryByRole('button', { name: 'Start service' })).toBeNull();
  expect(get.mock.calls.map((call) => call[1])).toEqual(['selected', 'different']);
});
it('does not render an assignment returned under the wrong ID', async () => {
  get.mockResolvedValue({ ...visit(), assignmentId: 'other' });
  render(element());
  await screen.findByRole('alert');
  expect(screen.queryByRole('article')).toBeNull();
});
it.each([401, 403, 404])(
  'clears the workspace when focus revalidation is denied: %s',
  async (status) => {
    render(element());
    await screen.findByRole('button', { name: 'Start service' });
    get.mockRejectedValue(new ApiRequestError(status, 'Denied'));
    fireEvent(window, new Event('focus'));
    expect(screen.queryByRole('article')).toBeNull();
    await screen.findByRole('alert');
  },
);
it('clears the workspace at the assignment deadline', async () => {
  vi.useFakeTimers();
  get.mockResolvedValue({ ...visit(), expiresAt: new Date(Date.now() + 1000).toISOString() });
  render(element());
  await act(async () => {});
  expect(screen.getByRole('article')).toBeDefined();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(screen.queryByRole('article')).toBeNull();
  expect(screen.getByRole('alert')).toBeDefined();
});
it('completes without trying to reopen now-closed content', async () => {
  const value = { ...visit(), status: 'IN_PROGRESS' as const };
  get.mockResolvedValue(value);
  vi.mocked(completeAssignment).mockResolvedValue({ ...value, status: 'COMPLETED', version: 3 });
  render(element());
  fireEvent.click(await screen.findByRole('button', { name: 'Complete service' }));
  const buttons = screen.getAllByRole('button', { name: 'Complete service' });
  fireEvent.click(buttons[buttons.length - 1]);
  await screen.findByText('This service is complete. Today’s schedule has been updated.');
  expect(screen.queryByRole('article')).toBeNull();
  expect(get).toHaveBeenCalledTimes(1);
});
it('rechecks another tab’s assignment update and clears stale commands', async () => {
  render(element());
  await screen.findByRole('button', { name: 'Start service' });
  get.mockRejectedValue(new ApiRequestError(404, 'Denied'));
  act(() => notifyAssignmentUpdated());
  expect(screen.queryByRole('article')).toBeNull();
  await screen.findByRole('alert');
});
