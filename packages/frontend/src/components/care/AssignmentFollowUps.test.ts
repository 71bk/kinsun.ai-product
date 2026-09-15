// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import type { AssignmentView } from '@/lib/api/assignments';
import { listCareActions, type CareActionListView } from '@/lib/api/care-actions';
import { ApiRequestError } from '@/lib/api/client';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { AssignmentFollowUps } from './AssignmentFollowUps';

vi.mock('@/lib/api/care-actions', () => ({ listCareActions: vi.fn() }));
const list = vi.mocked(listCareActions);
const config = { apiBaseUrl: '/backend/core' };
function visit(): AssignmentView {
  return {
    assignmentId: 'current',
    elderId: 'elder',
    status: 'IN_PROGRESS',
    version: 2,
    scheduledStart: new Date(Date.now() - 1000).toISOString(),
    scheduledEnd: new Date(Date.now() + 3600000).toISOString(),
    expiresAt: new Date(Date.now() + 3600000).toISOString(),
    scopeCount: 2,
    canReadCareActions: true,
  };
}
const tasks: CareActionListView = {
  items: [
    {
      careActionId: 'task',
      elderId: 'elder',
      title: 'Synthetic follow-up',
      status: 'OPEN',
      description: 'Synthetic details',
      dueAt: '2026-09-15T01:00:00Z',
    } as CareActionListView['items'][number],
  ],
  nextCursor: null,
  hasMore: false,
};
function element(value = visit(), onAccessCheck = vi.fn()) {
  return createElement(LocaleProvider, {
    initialLocale: 'en',
    children: createElement(AssignmentFollowUps, {
      key: value.assignmentId,
      assignment: value,
      config,
      onAccessCheck,
    }),
  });
}
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it('loads only when opened and binds every page to the same assignment', async () => {
  list
    .mockResolvedValueOnce({ ...tasks, nextCursor: 'cursor', hasMore: true })
    .mockResolvedValue({ ...tasks, items: [] });
  render(element());
  expect(list).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button'));
  await screen.findByText('Synthetic follow-up');
  fireEvent.click(screen.getByRole('button', { name: 'Next follow-up page' }));
  expect(screen.queryByText('Synthetic details')).toBeNull();
  await screen.findByText('There are no follow-up tasks available to view.');
  expect(list.mock.calls[1][2]).toMatchObject({
    assignmentId: 'current',
    cursor: 'cursor',
    statuses: ['OPEN', 'IN_PROGRESS', 'POSTPONED'],
  });
});
it.each(['CONFIRMED', 'COMPLETED', 'EXPIRED'] as const)(
  'has no follow-up entry before or after service: %s',
  (status) => {
    render(element({ ...visit(), status }));
    expect(screen.queryByRole('button')).toBeNull();
    expect(list).not.toHaveBeenCalled();
  },
);
it('does not request tasks without this assignment’s scope', () => {
  render(element({ ...visit(), canReadCareActions: false }));
  expect(screen.queryByRole('button')).toBeNull();
  expect(list).not.toHaveBeenCalled();
});
it.each([401, 403, 404, 500])('removes old tasks even when refresh fails: %s', async (status) => {
  vi.useFakeTimers();
  list
    .mockResolvedValueOnce(tasks)
    .mockRejectedValue(new ApiRequestError(status, 'Synthetic failure'));
  const deny = vi.fn();
  render(element(visit(), deny));
  fireEvent.click(screen.getByRole('button'));
  await act(async () => {});
  expect(screen.getByText('Synthetic follow-up')).toBeDefined();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30000);
  });
  expect(screen.queryByText('Synthetic details')).toBeNull();
  expect(deny).toHaveBeenCalledTimes(status === 500 ? 0 : 1);
});
it('never restores another assignment’s delayed response', async () => {
  let resolve!: (value: CareActionListView) => void;
  list.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const view = render(element());
  fireEvent.click(screen.getByRole('button'));
  view.rerender(element({ ...visit(), assignmentId: 'other' }));
  await act(async () => resolve(tasks));
  expect(screen.queryByText('Synthetic follow-up')).toBeNull();
});
it('clears tasks at expiry', async () => {
  vi.useFakeTimers();
  list.mockResolvedValue(tasks);
  const deny = vi.fn();
  render(element({ ...visit(), expiresAt: new Date(Date.now() + 1000).toISOString() }, deny));
  fireEvent.click(screen.getByRole('button'));
  await act(async () => {});
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(screen.queryByText('Synthetic follow-up')).toBeNull();
  expect(deny).toHaveBeenCalledOnce();
});
