// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import type { AssignmentView } from '@/lib/api/assignments';
import { ApiRequestError } from '@/lib/api/client';
import {
  getServiceRecord,
  submitServiceRecord,
  submitServiceRecordAndComplete,
  type ServiceRecordView,
} from '@/lib/api/service-records';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { ServiceRecordPanel } from './ServiceRecordPanel';

vi.mock('@/lib/api/service-records', () => ({
  getServiceRecord: vi.fn(),
  submitServiceRecord: vi.fn(),
  submitServiceRecordAndComplete: vi.fn(),
}));
const get = vi.mocked(getServiceRecord);
const submit = vi.mocked(submitServiceRecord);
const complete = vi.mocked(submitServiceRecordAndComplete);
const config = { apiBaseUrl: '/backend/core' };
function assignment(): AssignmentView {
  return {
    assignmentId: 'visit',
    elderId: 'elder',
    scheduledStart: new Date(Date.now() - 1000).toISOString(),
    scheduledEnd: new Date(Date.now() + 3600000).toISOString(),
    expiresAt: new Date(Date.now() + 3600000).toISOString(),
    status: 'IN_PROGRESS',
    scopeCount: 3,
    version: 2,
    canReadServiceRecord: true,
    canWriteServiceRecord: true,
  };
}
function record(): ServiceRecordView {
  return {
    service_record_id: 'record',
    assignment_id: 'visit',
    content: 'Synthetic submitted note',
    service_date: '2026-09-09',
    service_timezone: 'Asia/Taipei',
    completed_at: new Date().toISOString(),
    status: 'COMPLETED',
    version: 1,
  };
}
function mount(
  value = assignment(),
  onAccessCheck = vi.fn(),
  locale: 'en' | 'zh-Hant' = 'en',
  onCompleted = vi.fn(),
) {
  return render(
    createElement(LocaleProvider, {
      initialLocale: locale,
      children: createElement(ServiceRecordPanel, {
        assignment: value,
        config,
        onAccessCheck,
        onCompleted,
      }),
    }),
  );
}
async function prepare() {
  const textarea = await screen.findByRole('textbox');
  fireEvent.change(textarea, { target: { value: '  Synthetic visit note  ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Review and submit' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm record submission' }));
}
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it.each(['en', 'zh-Hant'] as const)('shows a submitted read-only record in %s', async (locale) => {
  get.mockResolvedValue(record());
  mount(assignment(), vi.fn(), locale);
  await screen.findByText('Synthetic submitted note');
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(submit).not.toHaveBeenCalled();
});
it('treats GET 404 as ambiguous and only submits after explicit confirmation', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Denied or missing'));
  submit.mockResolvedValue(record());
  mount();
  await screen.findByText(/No service record is currently readable/);
  expect(submit).not.toHaveBeenCalled();
  await prepare();
  await screen.findByText('Service record submitted');
  expect(submit).toHaveBeenCalledWith(
    config,
    'visit',
    { content: 'Synthetic visit note', expected_assignment_version: 2 },
    expect.stringMatching(/^service-record-/),
  );
});
it('preserves the exact payload and key after an uncertain submission', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
  submit.mockRejectedValueOnce(new TypeError('Network')).mockResolvedValue(record());
  mount();
  await prepare();
  const retry = await screen.findByRole('button', { name: 'Retry the same submission' });
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(true);
  fireEvent.click(retry);
  await screen.findByText('Service record submitted');
  expect(submit.mock.calls[1]).toEqual(submit.mock.calls[0]);
});
it('allows editing after a definite validation rejection and confirms a new attempt', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
  submit
    .mockRejectedValueOnce(new ApiRequestError(422, 'Invalid content'))
    .mockResolvedValue(record());
  mount();
  await prepare();
  await screen.findByText(/The content was not accepted/);
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(false);
  await prepare();
  await screen.findByText('Service record submitted');
  expect(submit.mock.calls[1][3]).not.toBe(submit.mock.calls[0][3]);
});
it.each([401, 403, 404])(
  'clears text and asks the owner to revalidate after POST %s',
  async (status) => {
    const access = vi.fn();
    get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
    submit.mockRejectedValue(new ApiRequestError(status, 'Denied'));
    mount(assignment(), access);
    await prepare();
    await screen.findByText(/The service record is unavailable/);
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(access).toHaveBeenCalledOnce();
  },
);
it('blocks a version/duplicate conflict without automatically retrying', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
  submit.mockRejectedValue(new ApiRequestError(409, 'Conflict'));
  mount();
  await prepare();
  await screen.findByText(/The assignment version changed/);
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(submit).toHaveBeenCalledOnce();
});
it('does not offer writing without the server-derived write capability', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
  mount({ ...assignment(), canWriteServiceRecord: false });
  await screen.findAllByText(/No service record is currently readable/);
  expect(screen.queryByRole('textbox')).toBeNull();
});
it('does not read or write an expired assignment', async () => {
  mount({ ...assignment(), expiresAt: new Date(Date.now() - 1).toISOString() });
  await screen.findByText(/The service record is unavailable/);
  expect(get).not.toHaveBeenCalled();
  expect(submit).not.toHaveBeenCalled();
});
it('ignores a response arriving after the page is hidden', async () => {
  let resolve!: (value: ServiceRecordView) => void;
  get.mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  mount();
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  fireEvent(document, new Event('visibilitychange'));
  await act(async () => resolve(record()));
  expect(screen.queryByText('Synthetic submitted note')).toBeNull();
});
it('clears an already-rendered record when its service window expires', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
  get.mockResolvedValue(record());
  mount({ ...assignment(), expiresAt: new Date(Date.now() + 1000).toISOString() });
  await act(async () => {});
  expect(screen.getByText('Synthetic submitted note')).toBeDefined();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1001);
  });
  expect(screen.queryByText('Synthetic submitted note')).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
});

async function prepareCompletion() {
  fireEvent.change(await screen.findByRole('textbox'), {
    target: { value: 'Synthetic combined note' },
  });
  fireEvent.click(screen.getByRole('checkbox', { name: /Also complete this visit/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Review and submit' }));
  expect(complete).not.toHaveBeenCalled();
  fireEvent.click(
    await screen.findByRole('button', { name: 'Confirm submission and complete visit' }),
  );
}
function receipt() {
  return {
    assignment_id: 'visit',
    service_record_id: 'record',
    assignment_version: 3,
    status: 'COMPLETED' as const,
  };
}

it('only offers combined completion with its own server-derived capability', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
  mount();
  await screen.findByRole('textbox');
  expect(screen.queryByRole('checkbox')).toBeNull();
});
it('confirms one combined command, clears content, and notifies the page', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
  complete.mockResolvedValue(receipt());
  const done = vi.fn();
  mount({ ...assignment(), canCompleteWithServiceRecord: true }, vi.fn(), 'en', done);
  await prepareCompletion();
  await screen.findByText('Service record submitted and visit completed.');
  expect(done).toHaveBeenCalledOnce();
  expect(submit).not.toHaveBeenCalled();
  expect(complete).toHaveBeenCalledOnce();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.queryByText('Synthetic combined note')).toBeNull();
});
it('freezes the combined mode, payload and key after an uncertain response', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
  complete.mockRejectedValueOnce(new TypeError('Network')).mockResolvedValue(receipt());
  mount({ ...assignment(), canCompleteWithServiceRecord: true });
  await prepareCompletion();
  const retry = await screen.findByRole('button', { name: 'Retry the same submission' });
  expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(true);
  fireEvent.click(retry);
  await screen.findByText('Service record submitted and visit completed.');
  expect(complete.mock.calls[1]).toEqual(complete.mock.calls[0]);
  expect(submit).not.toHaveBeenCalled();
});
it.each([401, 403, 404, 409])(
  'clears a combined command rejected with %s without claiming success',
  async (status) => {
    get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
    complete.mockRejectedValue(new ApiRequestError(status, 'Rejected'));
    const access = vi.fn();
    const done = vi.fn();
    mount({ ...assignment(), canCompleteWithServiceRecord: true }, access, 'en', done);
    await prepareCompletion();
    await screen.findByText(/The service record is unavailable/);
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByText('Service record submitted and visit completed.')).toBeNull();
    expect(done).not.toHaveBeenCalled();
    expect(access).toHaveBeenCalledTimes(status === 409 ? 0 : 1);
    expect(complete).toHaveBeenCalledOnce();
  },
);
it('ignores a combined success after the component is unmounted', async () => {
  get.mockRejectedValue(new ApiRequestError(404, 'Missing'));
  let resolve!: (value: ReturnType<typeof receipt>) => void;
  complete.mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const done = vi.fn();
  const view = mount({ ...assignment(), canCompleteWithServiceRecord: true }, vi.fn(), 'en', done);
  await prepareCompletion();
  view.unmount();
  await act(async () => resolve(receipt()));
  expect(done).not.toHaveBeenCalled();
});
