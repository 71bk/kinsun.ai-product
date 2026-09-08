import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import { getCaregiverDashboard } from './dashboard';

const config: ApiConfig = { apiBaseUrl: '/backend/core/' };

function success<T>(data: T): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: {
        correlation_id: 'synthetic-correlation',
        timestamp: '2026-08-13T00:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('getCaregiverDashboard', () => {
  it.each([0, 3, 105, null, undefined, -1, 1.5, '3'])(
    'maps only valid task counts without additional API requests: %s',
    async (count) => {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(success({ role: 'DAYCARE_CARE_WORKER', display_name: 'Worker' }))
        .mockResolvedValueOnce(success({
          items: [{ elder_id: 'elder', display_name: 'Elder', open_care_action_count: count, pending_event_review_count: count }],
          page: { has_more: false, next_cursor: null, limit: 100 },
        }));
      vi.stubGlobal('fetch', fetchMock);
      const result = await getCaregiverDashboard(config);
      expect(result.elders[0].openCareActionCount).toBe(
        typeof count === 'number' && Number.isInteger(count) && count >= 0 ? count : null,
      );
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(result.elders[0].pendingEventReviewCount).toBe(
        typeof count === 'number' && Number.isInteger(count) && count >= 0 ? count : null,
      );
    },
  );

  it('does not surface professional task counts to family even if supplied', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(success({ role: 'FAMILY_MEMBER', display_name: 'Family' }))
      .mockResolvedValueOnce(success({
        items: [{ elder_id: 'elder', display_name: 'Elder', open_care_action_count: 9, pending_event_review_count: 9 }],
        page: { has_more: false, next_cursor: null, limit: 100 },
      })));
    const elder = (await getCaregiverDashboard(config)).elders[0];
    expect(elder.openCareActionCount).toBeNull();
    expect(elder.pendingEventReviewCount).toBeNull();
  });
  it('derives the authorized-elder mode from Core identity and preserves cursor metadata', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/me')) {
        return success({ role: 'HOME_CARE_WORKER', display_name: 'Synthetic Worker' });
      }
      return success({
        items: [
          {
            elder_id: 'synthetic-elder',
            display_name: 'Synthetic Elder',
            care_unit_name: null,
            authorization_summary: 'assignment authorization',
          },
        ],
        page: { next_cursor: 'opaque-next', has_more: true, limit: 100 },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const dashboard = await getCaregiverDashboard(config);

    expect(String(fetchMock.mock.calls[1][0])).toContain('mode=home-care');
    expect(dashboard.actorRole).toBe('HOME_CARE_WORKER');
    expect(dashboard.actorName).toBe('Synthetic Worker');
    expect(dashboard.hasMore).toBe(true);
    expect(dashboard.elders).toEqual([
      {
        elderId: 'synthetic-elder',
        elderName: 'Synthetic Elder',
        careUnitName: null,
        authorizationSummary: 'assignment authorization',
        openCareActionCount: null,
        pendingEventReviewCount: null,
      },
    ]);
    expect(dashboard).not.toHaveProperty('total');
  });
});
