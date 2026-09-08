// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement, Suspense } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '@/lib/api/client';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import ElderDetailPage from './page';

const mocks = vi.hoisted(() => ({
  workspace: vi.fn(), actions: vi.fn(), candidates: vi.fn(), events: vi.fn(),
  create: vi.fn(), update: vi.fn(), adopt: vi.fn(), dismiss: vi.fn(), needsReview: vi.fn(), review: vi.fn(),
}));
vi.mock('@/lib/runtime-config', () => ({ getRuntimeConfig: async () => ({ credentialStatus: 'present', apiBaseUrl: '/backend/core' }) }));
vi.mock('@/lib/api/elders', () => ({ getElderWorkspace: mocks.workspace }));
vi.mock('@/lib/api/care-actions', () => ({
  listCareActions: mocks.actions, listCareActionCandidates: mocks.candidates,
  createCareAction: mocks.create, updateCareAction: mocks.update,
  adoptCareActionCandidate: mocks.adopt, dismissCareActionCandidate: mocks.dismiss,
}));
vi.mock('@/lib/api/events', () => ({ listEvents: mocks.events, summariseNeedsReview: mocks.needsReview, reviewEvent: mocks.review }));

const workspace = {
  elderId: 'synthetic-elder', displayName: 'Synthetic private elder',
  primaryCareSetting: 'DAYCARE', status: 'ACTIVE', purpose: 'care',
  allowedActions: ['care_action:read', 'care_action:create', 'care_action:update'],
  sourceType: 'relationship', sourceSummary: 'Synthetic private assignment', expiresAt: null,
};
const source = { eventId: 'source', elderId: 'synthetic-elder', eventType: 'MEAL',
  eventDate: '2026-09-07', content: 'Synthetic private source', status: 'VERIFIED',
  confidenceBand: 'HIGH', evidenceRefs: [], version: 1, consentVersion: 1, structuredPayload: {},
};
const action = { careActionId: 'action', elderId: 'synthetic-elder', actionType: 'FOLLOW_UP',
  title: 'Synthetic private action', triggerReason: 'Synthetic reason', description: null,
  relatedEventIds: ['source'], sourceEventProvenance: [], assigneeActorId: 'staff',
  dueAt: '2026-09-09T09:00:00Z', priority: 'MEDIUM', status: 'OPEN', resolution: null,
  createdByActorId: 'staff', version: 1, createdAt: '2026-09-07T09:00:00Z', updatedAt: '2026-09-07T09:00:00Z',
};
const candidate = { careActionCandidateId: 'candidate', elderId: 'synthetic-elder',
  actionType: 'FOLLOW_UP', suggestedTitle: 'Synthetic private candidate',
  triggerReason: 'Synthetic reason', sourceEventProvenance: [],
  suggestedDueAt: '2026-09-09T09:00:00Z', priority: 'MEDIUM', status: 'PENDING_REVIEW', version: 1,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.workspace.mockResolvedValue(workspace);
  mocks.actions.mockResolvedValue({ items: [action], hasMore: false, nextCursor: null });
  mocks.candidates.mockResolvedValue({ items: [candidate], hasMore: false, nextCursor: null });
  mocks.events.mockResolvedValue({ items: [source], nextCursor: null });
  mocks.needsReview.mockResolvedValue(null);
});
afterEach(cleanup);

async function openActions() {
  const params = Promise.resolve({ elderId: 'synthetic-elder' });
  await act(async () => {
    render(createElement(LocaleProvider, { initialLocale: 'zh-Hant', children:
      createElement(Suspense, { fallback: 'Loading' }, createElement(ElderDetailPage, { params })),
    }));
  });
  fireEvent.click(await screen.findByRole('tab', { name: '照護待辦' }));
  await screen.findByText('Synthetic private action');
  await screen.findByText('Synthetic private candidate');
  await screen.findByRole('button', { name: '建立待辦' });
}

async function submit(command: string) {
  if (command === 'create') {
    fireEvent.click(screen.getByRole('button', { name: '建立待辦' }));
    fireEvent.change(screen.getByLabelText('待辦標題'), { target: { value: 'Private unsaved title' } });
    fireEvent.change(screen.getByLabelText('建立原因'), { target: { value: 'Synthetic reason' } });
    fireEvent.submit(screen.getByRole('button', { name: '確認建立待辦' }).closest('form')!);
  } else if (command === 'update') {
    fireEvent.click(screen.getByRole('button', { name: '標記完成' }));
    fireEvent.change(screen.getByLabelText('處理紀錄／原因'), { target: { value: 'Private resolution' } });
    fireEvent.submit(screen.getByRole('button', { name: '確認更新狀態' }).closest('form')!);
  } else if (command === 'adopt') {
    fireEvent.click(screen.getByRole('button', { name: '檢視並採用' }));
    fireEvent.click(screen.getByRole('button', { name: '採用並建立待辦' }));
  } else {
    fireEvent.click(screen.getByRole('button', { name: command === 'exclude' ? '排除' : '拒絕' }));
    fireEvent.submit(screen.getByRole('button', { name: '確認不採用' }).closest('form')!);
  }
}

function expectHidden() {
  expect(screen.queryByText('Synthetic private elder')).toBeNull();
  expect(screen.queryByText('Synthetic private action')).toBeNull();
  expect(screen.queryByText('Synthetic private candidate')).toBeNull();
  expect(screen.queryByRole('tab')).toBeNull();
  expect(document.querySelector('input, textarea, select, [role="dialog"]')).toBeNull();
}

async function openPending(review = 'pending') {
  const params = Promise.resolve({ elderId: 'synthetic-elder' });
  const searchParams = Promise.resolve({ review });
  await act(async () => {
    render(createElement(LocaleProvider, { initialLocale: 'en', children:
      createElement(Suspense, { fallback: 'Loading' }, createElement(ElderDetailPage, { params, searchParams })),
    }));
  });
  await screen.findByRole('tab', { name: 'Care events' });
}

describe('dashboard pending review entry', () => {
  it('opens both pending states, pages with the same filter and deduplicates events', async () => {
    mocks.events.mockResolvedValueOnce({ items: [source], nextCursor: 'opaque' });
    await openPending();
    expect(mocks.events).toHaveBeenCalledWith(expect.anything(), 'synthetic-elder', { status: 'PENDING_REVIEW' });
    expect((screen.getByRole('combobox', { name: 'Status' }) as HTMLSelectElement).value).toBe('PENDING_REVIEW');
    mocks.events.mockResolvedValueOnce({ items: [source, { ...source, eventId: 'second', content: 'Synthetic second event' }], nextCursor: null });
    fireEvent.click(await screen.findByRole('button', { name: 'Load more events' }));
    await screen.findAllByText('Synthetic second event');
    expect(mocks.events).toHaveBeenLastCalledWith(expect.anything(), 'synthetic-elder', { status: 'PENDING_REVIEW', cursor: 'opaque' });
    expect(screen.queryByRole('button', { name: 'Load more events' })).toBeNull();
    expect(screen.getAllByText(source.content)).toHaveLength(2); // table + responsive card
  });

  it('ignores an unsupported review query', async () => {
    await openPending('all-private');
    expect(mocks.events).toHaveBeenCalledWith(expect.anything(), 'synthetic-elder', {});
  });

  it('discards an old page response after filters change', async () => {
    mocks.events.mockResolvedValueOnce({ items: [source], nextCursor: 'opaque' });
    await openPending();
    const pending = deferred<{ items: typeof source[]; nextCursor: string | null }>();
    mocks.events.mockReturnValueOnce(pending.promise);
    fireEvent.click(await screen.findByRole('button', { name: 'Load more events' }));
    mocks.events.mockResolvedValueOnce({ items: [], nextCursor: null });
    fireEvent.change(screen.getByRole('combobox', { name: 'Status' }), { target: { value: 'VERIFIED' } });
    await act(async () => pending.resolve({ items: [{ ...source, content: 'Stale private page' }], nextCursor: 'stale' }));
    expect(screen.queryByText('Stale private page')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Load more events' })).toBeNull();
  });

  it('clears private content when next-page authorization expires', async () => {
    mocks.events.mockResolvedValueOnce({ items: [source], nextCursor: 'opaque' });
    await openPending();
    mocks.events.mockRejectedValueOnce(new ApiRequestError(404, 'Resource not found'));
    mocks.workspace.mockRejectedValueOnce(new ApiRequestError(404, 'Resource not found'));
    fireEvent.click(await screen.findByRole('button', { name: 'Load more events' }));
    await waitFor(() => expect(mocks.workspace).toHaveBeenCalledTimes(2));
    expectHidden();
    expect(screen.queryByText(source.content)).toBeNull();
  });
});

describe('care command authorization recovery', () => {
  it.each(['create', 'update', 'adopt', 'reject', 'exclude'])('clears all elder surfaces immediately on %s denial', async (command) => {
    await openActions();
    const pending = deferred<typeof workspace>();
    mocks.workspace.mockReturnValueOnce(pending.promise);
    const mutation = mocks[command === 'reject' || command === 'exclude' ? 'dismiss' : command as 'create' | 'update' | 'adopt'];
    mutation.mockRejectedValueOnce(new ApiRequestError(404, 'Resource not found'));
    await submit(command);
    await waitFor(() => expect(mocks.workspace).toHaveBeenCalledTimes(2));
    expectHidden();
    await act(async () => pending.reject(new ApiRequestError(404, 'Resource not found')));
    await screen.findByRole('heading', { name: '沒有查看權限' });
    expectHidden();
    expect(mutation).toHaveBeenCalledTimes(1);
  });

  it.each([409, 422, 500])('does not discard input or revalidate for ordinary %s errors', async (status) => {
    await openActions();
    mocks.create.mockRejectedValueOnce(new ApiRequestError(status, 'Synthetic failure'));
    await submit('create');
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));
    await screen.findByRole('alert');
    expect(screen.getByDisplayValue('Private unsaved title')).toBeTruthy();
    expect(screen.getByText('Synthetic private elder')).toBeTruthy();
    expect(mocks.workspace).toHaveBeenCalledTimes(1);
  });

  it('does not interpret a resource 404 as elder-wide denial when access is still valid', async () => {
    await openActions();
    mocks.create.mockRejectedValueOnce(new ApiRequestError(404, 'Resource not found'));
    mocks.workspace.mockResolvedValueOnce({ ...workspace, allowedActions: ['care_action:read'] });
    await submit('create');
    await waitFor(() => expect(mocks.workspace).toHaveBeenCalledTimes(2));
    await screen.findByText('Synthetic private action');
    expect(screen.getByText('Synthetic private elder')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: '沒有查看權限' })).toBeNull();
    expect(screen.queryByRole('button', { name: '建立待辦' })).toBeNull();
    expect(screen.queryByRole('button', { name: '開始處理' })).toBeNull();
    expect(mocks.create).toHaveBeenCalledTimes(1);
  });

  it('fails closed on a failed access check and only retries by explicit user action', async () => {
    await openActions();
    mocks.workspace.mockRejectedValueOnce(new Error('Network unavailable'));
    mocks.create.mockRejectedValueOnce(new ApiRequestError(403, 'Denied'));
    await submit('create');
    fireEvent.click(await screen.findByRole('button', { name: '重試' }));
    await screen.findByText('Synthetic private action');
    expect(mocks.workspace).toHaveBeenCalledTimes(3);
    expect(mocks.create).toHaveBeenCalledTimes(1);
  });

  it('clears the workspace when the session expired', async () => {
    await openActions();
    mocks.workspace.mockRejectedValueOnce(new ApiRequestError(401, 'Authentication required'));
    mocks.create.mockRejectedValueOnce(new ApiRequestError(401, 'Authentication required'));
    await submit('create');
    await screen.findByRole('link', { name: '前往登入 →' });
    expectHidden();
  });

  it('bounds automatic checks when workspace succeeds but command lists keep denying access', async () => {
    await openActions();
    mocks.actions.mockRejectedValue(new ApiRequestError(403, 'Denied'));
    mocks.create.mockRejectedValueOnce(new ApiRequestError(404, 'Resource not found'));
    await submit('create');
    await screen.findByRole('button', { name: '重試' });
    expectHidden();
    expect(mocks.workspace).toHaveBeenCalledTimes(2);
  });

  it.each(['success', 'denial'])('ignores a late %s from an unmounted panel', async (outcome) => {
    mocks.actions.mockResolvedValueOnce({ items: [action], hasMore: true, nextCursor: 'next' });
    await openActions();
    const pending = deferred<{ items: typeof action[]; hasMore: boolean; nextCursor: null }>();
    mocks.actions.mockReturnValueOnce(pending.promise);
    fireEvent.click(screen.getByRole('button', { name: '載入更多待辦' }));
    await waitFor(() => expect(mocks.actions).toHaveBeenCalledTimes(2));
    mocks.workspace.mockRejectedValueOnce(new ApiRequestError(404, 'Resource not found'));
    mocks.create.mockRejectedValueOnce(new ApiRequestError(404, 'Resource not found'));
    await submit('create');
    await screen.findByRole('heading', { name: '沒有查看權限' });

    await act(async () => {
      if (outcome === 'success') {
        pending.resolve({ items: [action], hasMore: false, nextCursor: null });
      } else {
        pending.reject(new ApiRequestError(403, 'Denied'));
      }
    });
    expect(screen.getByRole('heading', { name: '沒有查看權限' })).toBeTruthy();
    expectHidden();
    expect(screen.queryByRole('button', { name: '重試' })).toBeNull();
    expect(mocks.workspace).toHaveBeenCalledTimes(2);
    expect(mocks.create).toHaveBeenCalledTimes(1);
  });
});
