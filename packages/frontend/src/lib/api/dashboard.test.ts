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
      },
    ]);
    expect(dashboard).not.toHaveProperty('total');
  });
});
