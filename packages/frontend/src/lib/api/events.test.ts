import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import { listEvents, reviewEvent, summariseNeedsReview, type EventView } from './events';

const config: ApiConfig = { apiBaseUrl: '/backend/core/' };

function success<T>(data: T): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: {
        correlation_id: 'correlation-1',
        timestamp: '2026-08-02T00:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}

function event(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 'event-1',
    elder_id: 'elder-1',
    event_type: 'MEAL',
    event_time: '2026-08-01T08:00:00Z',
    status: 'NEEDS_REVIEW',
    structured_payload: { summary: '早餐吃了粥' },
    evidence_refs: ['utterance-1'],
    confidence_band: 'LOW',
    version: 1,
    consent_version: 1,
    created_at: '2026-08-01T08:00:00Z',
    updated_at: '2026-08-01T08:00:00Z',
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('listEvents', () => {
  it('requests both pending statuses in one cursor-paginated server query', async () => {
    const fetchMock = vi.fn(async () => success({ items: [], next_cursor: null, has_more: false }));
    vi.stubGlobal('fetch', fetchMock);
    await listEvents(config, 'elder-1', { status: 'PENDING_REVIEW', cursor: 'opaque' });
    const url = new URL(String((fetchMock.mock.calls as unknown[][])[0][0]), 'http://frontend.test');
    expect(url.searchParams.getAll('status')).toEqual(['CANDIDATE', 'NEEDS_REVIEW']);
    expect(url.searchParams.get('cursor')).toBe('opaque');
    expect(url.searchParams.get('limit')).toBe('100');
  });
  it('sends date and event-type filters to Core before cursor pagination', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success({ items: [], next_cursor: null, has_more: false }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await listEvents(config, 'elder-1', {
      dateFrom: '2026-08-01',
      dateTo: '2026-08-02',
      eventType: 'MEAL',
      status: 'VERIFIED',
      cursor: 'opaque-cursor',
    });

    const [url] = fetchMock.mock.calls[0];
    const parsed = new URL(String(url), 'http://frontend.test');
    expect(parsed.searchParams.get('date_from')).toBe('2026-08-01');
    expect(parsed.searchParams.get('date_to')).toBe('2026-08-02');
    expect(parsed.searchParams.get('event_type')).toBe('MEAL');
    expect(parsed.searchParams.get('status')).toBe('VERIFIED');
    expect(parsed.searchParams.get('cursor')).toBe('opaque-cursor');
  });

  /* B04: the source filter is a Core query parameter, never a browser-side
     narrowing of a page, and it is simply absent when "all sources" is chosen. */
  it('sends the recorded-source filter to Core and omits it for all sources', async () => {
    const fetchMock = vi.fn<Parameters<typeof fetch>, Promise<Response>>(async () =>
      success({ items: [], next_cursor: null, has_more: false }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await listEvents(config, 'elder-1', { sourceType: 'CONVERSATION_SESSION' });
    await listEvents(config, 'elder-1', {});

    const first = new URL(String(fetchMock.mock.calls[0][0]), 'http://frontend.test');
    const second = new URL(String(fetchMock.mock.calls[1][0]), 'http://frontend.test');
    expect(first.searchParams.get('source_type')).toBe('CONVERSATION_SESSION');
    expect(second.searchParams.has('source_type')).toBe(false);
  });
});

/* B03: the review request's omit / set / clear semantics are the contract's,
   so the client must not echo unchanged values or send null for the type. */
describe('reviewEvent', () => {
  const view: EventView = {
    eventId: 'event-1',
    elderId: 'elder-1',
    eventType: 'MEAL',
    eventDate: '2026-08-01',
    eventTime: '2026-08-01T08:00:00Z',
    content: '早餐吃了粥',
    status: 'NEEDS_REVIEW',
    confidenceBand: 'LOW',
    evidenceRefs: ['utterance-1'],
    version: 1,
    consentVersion: 1,
    structuredPayload: { summary: '早餐吃了粥' },
  };

  async function bodyOf(
    decision: Parameters<typeof reviewEvent>[3],
    correction?: Parameters<typeof reviewEvent>[4],
  ) {
    const fetchMock = vi.fn(async () => success(event({ status: 'CORRECTED', version: 2 })));
    vi.stubGlobal('fetch', fetchMock);
    await reviewEvent(config, 'elder-1', view, decision, correction);
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    return JSON.parse(String(init.body)) as Record<string, unknown>;
  }

  it('omits type and time when a correction leaves them unchanged', async () => {
    const body = await bodyOf('CORRECT', { content: '早餐吃了稀飯', eventType: 'MEAL' });
    expect(body.corrected_payload).toEqual({ summary: '早餐吃了稀飯' });
    expect(body).not.toHaveProperty('corrected_event_type');
    expect(body).not.toHaveProperty('corrected_event_time');
  });

  it('sends a changed type and a timezone-qualified new time', async () => {
    const body = await bodyOf('CORRECT', {
      content: '午睡了一小時',
      eventType: 'SLEEP',
      eventTime: '2026-08-01T13:00:00.000Z',
    });
    expect(body.corrected_event_type).toBe('SLEEP');
    expect(body.corrected_event_time).toBe('2026-08-01T13:00:00.000Z');
    expect(String(body.corrected_event_time)).toMatch(/(?:Z|[+-]\d{2}:\d{2})$/);
  });

  it('sends null to clear the time, and never sends null for the type', async () => {
    const body = await bodyOf('CORRECT', { content: '早餐吃了粥', eventTime: null });
    expect(body.corrected_event_time).toBeNull();
    expect(body).not.toHaveProperty('corrected_event_type');
  });

  it('never attaches correction fields to a non-CORRECT decision', async () => {
    const body = await bodyOf('VERIFY', { content: 'ignored', eventType: 'SLEEP', eventTime: null });
    expect(body.corrected_payload).toBeNull();
    expect(body).not.toHaveProperty('corrected_event_type');
    expect(body).not.toHaveProperty('corrected_event_time');
    expect(body.expected_version).toBe(1);
  });
});

describe('summariseNeedsReview', () => {
  it('asks Core for the review queue rather than filtering a page in the browser', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success({ items: [], next_cursor: null, has_more: false }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await summariseNeedsReview(config, 'elder-1');

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('status=NEEDS_REVIEW');
    expect(String(url)).toContain('status=CANDIDATE');
  });

  it('counts the queue and breaks it down by confidence band', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        success({
          items: [
            event({ event_id: 'a', confidence_band: 'LOW' }),
            event({ event_id: 'b', confidence_band: 'LOW' }),
            event({ event_id: 'c', confidence_band: 'MEDIUM' }),
          ],
          next_cursor: null,
          has_more: false,
        }),
      ),
    );

    const summary = await summariseNeedsReview(config, 'elder-1');

    expect(summary.count).toBe(3);
    expect(summary.byConfidence).toEqual({ LOW: 2, MEDIUM: 1, HIGH: 0 });
    expect(summary.atLeast).toBe(false);
  });

  /* Pagination is opaque-cursor only and exposes no total (AGENTS.md §8.1), so
     a further page means the number shown is a floor. Presenting it as exact
     would state an unknown as a fact (§4). */
  it('marks the count as a lower bound when Core has another page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        success({ items: [event()], next_cursor: 'opaque-cursor', has_more: true }),
      ),
    );

    const summary = await summariseNeedsReview(config, 'elder-1');

    expect(summary.count).toBe(1);
    expect(summary.atLeast).toBe(true);
  });

  it('reports an empty queue without inventing a band', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => success({ items: [], next_cursor: null, has_more: false })),
    );

    const summary = await summariseNeedsReview(config, 'elder-1');

    expect(summary.count).toBe(0);
    expect(summary.byConfidence).toEqual({ LOW: 0, MEDIUM: 0, HIGH: 0 });
  });
});
