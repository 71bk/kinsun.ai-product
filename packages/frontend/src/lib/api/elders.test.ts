import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import { getElderWorkspace } from './elders';

const config: ApiConfig = { apiBaseUrl: '/backend/core' };

function response(data: unknown, status = 200): Response {
  return new Response(
    JSON.stringify(
      status === 200
        ? {
            data,
            meta: {
              correlation_id: 'synthetic-correlation',
              timestamp: '2026-08-13T00:00:00Z',
              schema_version: '1.0',
            },
          }
        : { error: { message: 'Resource not found' } },
    ),
    { status, headers: { 'Content-Type': 'application/json' } },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('getElderWorkspace', () => {
  it('returns identity only after both elder and access-context reads succeed', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return url.endsWith('/access-context')
        ? response({
            purpose: 'care delivery',
            allowed_actions: ['care_event:read', 'summary:review'],
            source_type: 'assignment',
            source_summary: 'assignment authorization',
            expires_at: '2026-08-13T10:00:00Z',
          })
        : response({
            elder_id: 'synthetic-elder',
            display_name: 'Synthetic Elder',
            primary_care_setting: 'HOME_CARE',
            status: 'ACTIVE',
          });
    });
    vi.stubGlobal('fetch', fetchMock);

    const workspace = await getElderWorkspace(config, 'synthetic-elder');

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(workspace.displayName).toBe('Synthetic Elder');
    expect(workspace.allowedActions).toContain('summary:review');
  });

  it('rejects the whole read when access-context returns the non-disclosing 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).endsWith('/access-context')
          ? response(null, 404)
          : response({
              elder_id: 'synthetic-elder',
              display_name: 'Must not be returned',
              primary_care_setting: 'HOME_CARE',
              status: 'ACTIVE',
            }),
      ),
    );

    await expect(getElderWorkspace(config, 'synthetic-elder')).rejects.toMatchObject({
      status: 404,
    });
  });
});
