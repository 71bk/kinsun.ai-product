// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import type { AssignmentView } from '@/lib/api/assignments';
import { ApiRequestError } from '@/lib/api/client';
import { getPreviousServiceRecord, type PreviousServiceRecord } from '@/lib/api/service-records';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { PreviousServiceRecordPanel } from './PreviousServiceRecordPanel';

vi.mock('@/lib/api/service-records', () => ({ getPreviousServiceRecord: vi.fn() }));
const get = vi.mocked(getPreviousServiceRecord);
const config = { apiBaseUrl: '/backend/core' };
const note: PreviousServiceRecord = {
  service_record_id: 'record',
  source_assignment_id: 'previous',
  service_date: '2026-09-13',
  service_timezone: 'Asia/Taipei',
  completed_at: '2026-09-13T01:00:00Z',
  version: 1,
  content: 'Synthetic handover from another worker',
};
function assignment(): AssignmentView {
  return {
    assignmentId: 'current',
    elderId: 'elder',
    status: 'IN_PROGRESS',
    version: 2,
    scheduledStart: new Date(Date.now() - 3600000).toISOString(),
    scheduledEnd: new Date(Date.now() + 3600000).toISOString(),
    expiresAt: new Date(Date.now() + 3600000).toISOString(),
    scopeCount: 2,
    canReadPreviousServiceRecord: true,
  };
}
function element(value = assignment(), onAccessCheck = vi.fn(), locale: 'en' | 'zh-Hant' = 'en') {
  return createElement(LocaleProvider, {
    initialLocale: locale,
    children: createElement(PreviousServiceRecordPanel, {
      assignment: value,
      config,
      onAccessCheck,
    }),
  });
}
async function open() {
  fireEvent.click(await screen.findByRole('button', { name: 'View previous service record' }));
}
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it.each(['en', 'zh-Hant'] as const)(
  'loads only on explicit opening and clears on close in %s',
  async (locale) => {
    get.mockResolvedValue(note);
    render(element(assignment(), vi.fn(), locale));
    expect(get).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button'));
    await screen.findByText(note.content);
    expect(screen.getByText(/2026-09-13.*Asia\/Taipei/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button'));
    expect(screen.queryByText(note.content)).toBeNull();
    expect(get.mock.calls[0][1]).toBe('current');
  },
);
it('distinguishes an authorized empty result from a failed request', async () => {
  get.mockResolvedValue(null);
  render(element());
  await open();
  await screen.findByText('No previous service record is currently available.');
  expect(screen.queryByRole('alert')).toBeNull();
});
it.each([401, 403, 404])('clears content and checks access on %s revalidation', async (status) => {
  vi.useFakeTimers();
  get
    .mockResolvedValueOnce(note)
    .mockRejectedValueOnce(new ApiRequestError(status, 'Synthetic denial'));
  const check = vi.fn();
  render(element(assignment(), check));
  fireEvent.click(screen.getByRole('button'));
  await act(async () => {
    await Promise.resolve();
  });
  expect(screen.getByText(note.content)).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30000);
  });
  expect(screen.queryByText(note.content)).toBeNull();
  expect(check).toHaveBeenCalledTimes(1);
});
it('does not retain a note when refresh fails and allows a fresh retry', async () => {
  vi.useFakeTimers();
  get
    .mockResolvedValueOnce(note)
    .mockRejectedValueOnce(new TypeError('Synthetic network'))
    .mockResolvedValueOnce(note);
  render(element());
  fireEvent.click(screen.getByRole('button'));
  await act(async () => {
    await Promise.resolve();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30000);
  });
  expect(screen.queryByText(note.content)).toBeNull();
  expect(screen.getByRole('alert')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  await act(async () => {
    await Promise.resolve();
  });
  expect(screen.getByText(note.content)).toBeTruthy();
});
it('discards a delayed response after hiding and reauthorizes on return', async () => {
  let resolve!: (value: PreviousServiceRecord) => void;
  get
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockResolvedValueOnce(null);
  render(element());
  await open();
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  fireEvent(document, new Event('visibilitychange'));
  await act(async () => {
    resolve(note);
  });
  expect(screen.queryByText(note.content)).toBeNull();
  hidden.mockReturnValue(false);
  fireEvent(document, new Event('visibilitychange'));
  await screen.findByText('No previous service record is currently available.');
  expect(get).toHaveBeenCalledTimes(2);
});
it('clears on expiry without keeping the history entry', async () => {
  vi.useFakeTimers();
  get.mockResolvedValue(note);
  const value = assignment();
  value.expiresAt = new Date(Date.now() + 1000).toISOString();
  const check = vi.fn();
  render(element(value, check));
  fireEvent.click(screen.getByRole('button'));
  await act(async () => {
    await Promise.resolve();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(screen.queryByText(note.content)).toBeNull();
  expect(screen.queryByRole('button')).toBeNull();
  expect(check).toHaveBeenCalledTimes(1);
});
it.each(['no_scope', 'CONFIRMED', 'COMPLETED', 'expired'])('does not fetch when %s', (mode) => {
  const value = assignment();
  if (mode === 'no_scope') value.canReadPreviousServiceRecord = false;
  else if (mode === 'expired') value.expiresAt = new Date(Date.now() - 1).toISOString();
  else value.status = mode as 'CONFIRMED' | 'COMPLETED';
  render(element(value));
  expect(screen.queryByRole('button')).toBeNull();
  expect(get).not.toHaveBeenCalled();
});
it('does not render a response from a different assignment after props change', async () => {
  let resolve!: (value: PreviousServiceRecord) => void;
  get
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockResolvedValueOnce(null);
  const check = vi.fn();
  const value = assignment();
  const view = render(element(value, check));
  await open();
  view.rerender(element({ ...value, assignmentId: 'next' }, check));
  await screen.findByText('No previous service record is currently available.');
  await act(async () => {
    resolve(note);
  });
  expect(screen.queryByText(note.content)).toBeNull();
});
