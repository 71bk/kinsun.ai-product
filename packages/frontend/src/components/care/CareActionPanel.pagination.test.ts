// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  adoptCareActionCandidate,
  dismissCareActionCandidate,
  listCareActionCandidates,
  listCareActions,
  type CareActionCandidateListView,
  type CareActionCandidateView,
  type CareActionListView,
  type CareActionView,
} from '@/lib/api/care-actions';
import { listEvents, type EventView, type ListEventsResult } from '@/lib/api/events';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { CareActionPanel } from './CareActionPanel';

vi.mock('@/lib/api/care-actions', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/care-actions')>('@/lib/api/care-actions');
  return {
    ...actual,
    adoptCareActionCandidate: vi.fn(),
    dismissCareActionCandidate: vi.fn(),
    listCareActionCandidates: vi.fn(),
    listCareActions: vi.fn(),
  };
});

vi.mock('@/lib/api/events', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/events')>('@/lib/api/events');
  return { ...actual, listEvents: vi.fn() };
});

const listCareActionsMock = vi.mocked(listCareActions);
const listCareActionCandidatesMock = vi.mocked(listCareActionCandidates);
const adoptCareActionCandidateMock = vi.mocked(adoptCareActionCandidate);
const dismissCareActionCandidateMock = vi.mocked(dismissCareActionCandidate);
const listEventsMock = vi.mocked(listEvents);

function action(id: string, title: string): CareActionView {
  return {
    careActionId: id,
    elderId: 'synthetic-elder',
    actionType: 'FOLLOW_UP',
    title,
    description: null,
    triggerReason: 'Synthetic reviewed event',
    relatedEventIds: ['synthetic-event'],
    sourceEventProvenance: [],
    assigneeActorId: 'synthetic-worker',
    dueAt: '2026-09-05T01:00:00Z',
    priority: 'MEDIUM',
    status: 'OPEN',
    resolution: null,
    createdByActorId: 'synthetic-worker',
    version: 1,
    createdAt: '2026-09-04T01:00:00Z',
    updatedAt: '2026-09-04T01:00:00Z',
  };
}

function sourceEvent(id: string, status: EventView['status']): EventView {
  return {
    eventId: id,
    elderId: 'synthetic-elder',
    eventType: 'MEAL',
    eventDate: '2026-09-04',
    content: `Synthetic event ${id}`,
    status,
    confidenceBand: 'HIGH',
    evidenceRefs: [],
    version: 1,
    consentVersion: 1,
    structuredPayload: { summary: `Synthetic event ${id}` },
  };
}

function candidate(id = 'candidate-1'): CareActionCandidateView {
  return {
    careActionCandidateId: id,
    elderId: 'synthetic-elder',
    actionType: 'CONTACT_FAMILY',
    suggestedTitle: '確認預期聯繫狀況',
    triggerReason: '預期聯繫未發生，需要由照護者確認。',
    sourceEventProvenance: [],
    suggestedDueAt: '2026-09-05T09:00:00+08:00',
    priority: 'MEDIUM',
    status: 'PENDING_REVIEW',
    dispositionReasonCode: null,
    dispositionNotes: null,
    decidedByActorId: null,
    decidedAt: null,
    adoptedCareActionId: null,
    extractorVersion: 'care-action-candidate-v1',
    version: 1,
    createdAt: '2026-09-04T08:00:00+08:00',
    updatedAt: '2026-09-04T08:00:00+08:00',
  };
}

function renderPanel({ canCreate = true, canUpdate = false } = {}) {
  return render(
    createElement(LocaleProvider, {
      initialLocale: 'zh-Hant',
      children: createElement(CareActionPanel, {
        apiConfig: { apiBaseUrl: '/backend/core' },
        elderId: 'synthetic-elder',
        canCreate,
        canUpdate,
      }),
    }),
  );
}

beforeEach(() => {
  listCareActionCandidatesMock.mockResolvedValue({
    items: [],
    nextCursor: null,
    hasMore: false,
  } satisfies CareActionCandidateListView);
  listCareActionsMock.mockImplementation(async (_config, _elderId, options = {}) => {
    if (options.cursor === 'actions-next') {
      return {
        items: [action('action-2', '第二頁待辦')],
        nextCursor: null,
        hasMore: false,
      } satisfies CareActionListView;
    }
    return {
      items: [action('action-1', '第一頁待辦')],
      nextCursor: 'actions-next',
      hasMore: true,
    } satisfies CareActionListView;
  });

  listEventsMock.mockImplementation(async (_config, _elderId, filters = {}) => {
    if (filters.cursor) {
      return {
        items: [sourceEvent(`${filters.status?.toLowerCase()}-2`, filters.status ?? 'VERIFIED')],
        nextCursor: null,
      } satisfies ListEventsResult;
    }
    return {
      items: [sourceEvent(`${filters.status?.toLowerCase()}-1`, filters.status ?? 'VERIFIED')],
      nextCursor: `${filters.status?.toLowerCase()}-next`,
    } satisfies ListEventsResult;
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('CareActionPanel pagination', () => {
  it('appends the next Care Action page and removes the exhausted control', async () => {
    renderPanel();
    await screen.findByText('第一頁待辦');

    fireEvent.click(screen.getByRole('button', { name: '載入更多待辦' }));

    await screen.findByText('第二頁待辦');
    expect(screen.getByText('第一頁待辦')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '載入更多待辦' })).toBeNull();
    expect(listCareActionsMock).toHaveBeenLastCalledWith(
      { apiBaseUrl: '/backend/core' },
      'synthetic-elder',
      { cursor: 'actions-next' },
    );
  });

  it('advances VERIFIED and CORRECTED source cursors independently', async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(listEventsMock).toHaveBeenCalledTimes(2));
    const createToggle = container.querySelector<HTMLButtonElement>('button[aria-expanded]');
    expect(createToggle).not.toBeNull();
    fireEvent.click(createToggle!);

    const sourceSelect = container.querySelector<HTMLSelectElement>('select[name="sourceEvent"]');
    expect(sourceSelect?.options).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '載入更多來源事件' }));

    await waitFor(() => expect(sourceSelect?.options).toHaveLength(4));
    expect(screen.queryByRole('button', { name: '載入更多來源事件' })).toBeNull();
    expect(listEventsMock).toHaveBeenCalledWith(
      { apiBaseUrl: '/backend/core' },
      'synthetic-elder',
      { status: 'VERIFIED', cursor: 'verified-next' },
    );
    expect(listEventsMock).toHaveBeenCalledWith(
      { apiBaseUrl: '/backend/core' },
      'synthetic-elder',
      { status: 'CORRECTED', cursor: 'corrected-next' },
    );
  });

  it('adopts an AI candidate only after explicit confirmation and refreshes formal actions', async () => {
    const pending = candidate();
    listCareActionCandidatesMock.mockResolvedValueOnce({
      items: [pending],
      nextCursor: null,
      hasMore: false,
    });
    adoptCareActionCandidateMock.mockResolvedValue({
      ...pending,
      status: 'ADOPTED',
      adoptedCareActionId: 'action-created-from-candidate',
      dispositionReasonCode: 'HUMAN_CONFIRMED',
      decidedByActorId: 'synthetic-worker',
      decidedAt: '2026-09-04T09:00:00+08:00',
      version: 2,
    });
    renderPanel({ canCreate: true, canUpdate: true });
    await screen.findByText('確認預期聯繫狀況');

    fireEvent.click(screen.getByRole('button', { name: '檢視並採用' }));
    fireEvent.click(screen.getByRole('button', { name: '採用並建立待辦' }));

    await waitFor(() => expect(adoptCareActionCandidateMock).toHaveBeenCalledTimes(1));
    expect(adoptCareActionCandidateMock).toHaveBeenCalledWith(
      { apiBaseUrl: '/backend/core' },
      'synthetic-elder',
      pending,
      expect.objectContaining({
        title: '確認預期聯繫狀況',
        priority: 'MEDIUM',
        dueAt: expect.any(String),
      }),
    );
    await waitFor(() => expect(screen.queryByText('確認預期聯繫狀況')).toBeNull());
    expect(listCareActionsMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('records a reject reason without refreshing or creating a formal action', async () => {
    const pending = candidate();
    listCareActionCandidatesMock.mockResolvedValueOnce({
      items: [pending],
      nextCursor: null,
      hasMore: false,
    });
    dismissCareActionCandidateMock.mockResolvedValue({
      ...pending,
      status: 'REJECTED',
      dispositionReasonCode: 'ALREADY_HANDLED',
      dispositionNotes: '已完成聯繫',
      decidedByActorId: 'synthetic-worker',
      decidedAt: '2026-09-04T09:00:00+08:00',
      version: 2,
    });
    renderPanel({ canCreate: true, canUpdate: true });
    await screen.findByText('確認預期聯繫狀況');
    const actionCallsBeforeDismissal = listCareActionsMock.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: '拒絕' }));
    fireEvent.change(screen.getByLabelText('原因'), { target: { value: 'ALREADY_HANDLED' } });
    fireEvent.change(screen.getByLabelText('補充說明（選填）'), {
      target: { value: '已完成聯繫' },
    });
    fireEvent.click(screen.getByRole('button', { name: '確認不採用' }));

    await waitFor(() => expect(dismissCareActionCandidateMock).toHaveBeenCalledTimes(1));
    expect(dismissCareActionCandidateMock).toHaveBeenCalledWith(
      { apiBaseUrl: '/backend/core' },
      'synthetic-elder',
      pending,
      {
        decision: 'REJECT',
        reasonCode: 'ALREADY_HANDLED',
        notes: '已完成聯繫',
      },
    );
    expect(adoptCareActionCandidateMock).not.toHaveBeenCalled();
    expect(listCareActionsMock).toHaveBeenCalledTimes(actionCallsBeforeDismissal);
  });
});
