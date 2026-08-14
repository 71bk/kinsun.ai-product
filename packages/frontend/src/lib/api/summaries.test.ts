import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import { generateSummary, reviewSummary, type SummaryView } from './summaries';

const config: ApiConfig = { apiBaseUrl: '/backend/core' };

const summary: SummaryView = {
  summaryId: 'synthetic-summary',
  elderId: 'synthetic-elder',
  date: '2026-08-13',
  status: 'NEEDS_REVIEW',
  items: [],
  missingFields: [],
  conflictFlags: [],
  version: 7,
  generatedAt: null,
  updatedAt: '2026-08-13T00:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('reviewSummary', () => {
  it('uses the existing review contract without publishing a report', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(
          JSON.stringify({
            data: {
              summary_id: 'synthetic-summary',
              elder_id: 'synthetic-elder',
              summary_date: '2026-08-13',
              summary_type: 'PROFESSIONAL_DAILY',
              status: 'READY',
              items: [],
              missing_fields: [],
              conflict_flags: [],
              version: 7,
              generated_at: null,
              created_at: '2026-08-13T00:00:00Z',
              updated_at: '2026-08-13T00:00:00Z',
              review_record_id: 'synthetic-review',
            },
            meta: {
              correlation_id: 'synthetic-correlation',
              timestamp: '2026-08-13T00:00:00Z',
              schema_version: '1.0',
            },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await reviewSummary(config, 'synthetic-elder', summary, 'VERIFY');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/synthetic-summary/review');
    expect(new Headers(init?.headers).get('Idempotency-Key')).toMatch('summary-review-');
    expect(JSON.parse(String(init?.body))).toEqual({
      decision: 'VERIFY',
      reason_code: 'CAREGIVER_UI_REVIEW',
      expected_version: 7,
    });
    expect(result.status).toBe('READY');
  });
});

describe('generateSummary', () => {
  it('posts only the selected date with an idempotency key', async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) =>
      new Response(
        JSON.stringify({
          data: {
            summary_id: 'synthetic-summary',
            elder_id: 'synthetic-elder',
            summary_date: '2026-08-14',
            summary_type: 'PROFESSIONAL_DAILY',
            status: 'NEEDS_REVIEW',
            items: [],
            missing_fields: ['MEAL'],
            conflict_flags: [],
            version: 1,
            generated_at: '2026-08-14T00:00:00Z',
            created_at: '2026-08-14T00:00:00Z',
            updated_at: '2026-08-14T00:00:00Z',
          },
          meta: {},
        }),
        { status: 201, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await generateSummary(config, 'synthetic-elder', '2026-08-14');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/summaries/generate');
    expect(new Headers(init?.headers).get('Idempotency-Key')).toMatch('summary-generate-');
    expect(JSON.parse(String(init?.body))).toEqual({ summary_date: '2026-08-14' });
  });
});
