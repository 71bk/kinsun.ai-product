// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  listCareActions,
  type CareActionListView,
  type CareActionView,
} from '@/lib/api/care-actions';
import { listEvents, type EventView, type ListEventsResult } from '@/lib/api/events';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { CareActionPanel } from './CareActionPanel';

vi.mock('@/lib/api/care-actions', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/care-actions')>(
    '@/lib/api/care-actions',
  );
  return { ...actual, listCareActions: vi.fn() };
});

vi.mock('@/lib/api/events', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/events')>('@/lib/api/events');
  return { ...actual, listEvents: vi.fn() };
});

const listCareActionsMock = vi.mocked(listCareActions);
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

function renderPanel() {
  return render(
    createElement(
      LocaleProvider,
      {
        initialLocale: 'zh-Hant',
        children: createElement(CareActionPanel, {
          apiConfig: { apiBaseUrl: '/backend/core' },
          elderId: 'synthetic-elder',
          canCreate: true,
          canUpdate: false,
        }),
      },
    ),
  );
}

beforeEach(() => {
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
});
