import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import {
  createCareAction,
  listCareActions,
  updateCareAction,
  type CareActionView,
} from './care-actions';

const config: ApiConfig = { apiBaseUrl: '/backend/core' };

function success<T>(data: T, status = 200): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: {
        correlation_id: 'synthetic-correlation',
        timestamp: '2026-09-02T00:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status, headers: { 'Content-Type': 'application/json' } },
  );
}

function coreAction(status = 'OPEN', version = 1) {
  return {
    care_action_id: 'synthetic-action',
    elder_id: 'synthetic-elder',
    action_type: 'FOLLOW_UP',
    title: 'Follow up after lunch',
    description: null,
    trigger_reason: 'A professional reviewed the source event',
    related_event_ids: ['synthetic-event'],
    source_event_provenance: [
      {
        event_id: 'synthetic-event',
        event_version_id: 'synthetic-event-version',
        event_version: 1,
        event_type: 'MEAL',
        event_time: '2026-09-02T00:30:00Z',
        source_status: 'VERIFIED',
        snapshot_sha256: 'a'.repeat(64),
        snapshot_schema_version: 'care-event-provenance.v1',
      },
    ],
    assignee_actor_id: 'synthetic-worker',
    due_at: '2026-09-03T01:00:00Z',
    priority: 'MEDIUM',
    status,
    resolution: status === 'COMPLETED' ? 'Completed with the elder' : null,
    created_by_actor_id: 'synthetic-worker',
    version,
    created_at: '2026-09-02T01:00:00Z',
    updated_at: '2026-09-02T01:00:00Z',
  };
}

const action: CareActionView = {
  careActionId: 'synthetic-action',
  elderId: 'synthetic-elder',
  actionType: 'FOLLOW_UP',
  title: 'Follow up after lunch',
  description: null,
  triggerReason: 'A professional reviewed the source event',
  relatedEventIds: ['synthetic-event'],
  sourceEventProvenance: [
    {
      eventId: 'synthetic-event',
      eventVersionId: 'synthetic-event-version',
      eventVersion: 1,
      eventType: 'MEAL',
      eventTime: '2026-09-02T00:30:00Z',
      sourceStatus: 'VERIFIED',
      snapshotSha256: 'a'.repeat(64),
      snapshotSchemaVersion: 'care-event-provenance.v1',
    },
  ],
  assigneeActorId: 'synthetic-worker',
  dueAt: '2026-09-03T01:00:00Z',
  priority: 'MEDIUM',
  status: 'OPEN',
  resolution: null,
  createdByActorId: 'synthetic-worker',
  version: 1,
  createdAt: '2026-09-02T01:00:00Z',
  updatedAt: '2026-09-02T01:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('care action API boundary', () => {
  it('uses repeated status filters and preserves opaque pagination metadata', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success({ items: [coreAction()], next_cursor: 'opaque-next', has_more: true }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await listCareActions(config, 'synthetic-elder', ['OPEN', 'IN_PROGRESS']);

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('status=OPEN');
    expect(url).toContain('status=IN_PROGRESS');
    expect(url).not.toContain('offset');
    expect(result).toEqual({ items: [action], nextCursor: 'opaque-next', hasMore: true });
  });

  it('creates a self-assigned action with formal source ids and an idempotency key', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success(coreAction(), 201),
    );
    vi.stubGlobal('fetch', fetchMock);

    await createCareAction(config, 'synthetic-elder', {
      actionType: 'FOLLOW_UP',
      title: 'Follow up after lunch',
      triggerReason: 'A professional reviewed the source event',
      relatedEventIds: ['synthetic-event'],
      dueAt: '2026-09-03T01:00:00Z',
      priority: 'MEDIUM',
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Idempotency-Key')).toMatch('care-action-create-');
    expect(JSON.parse(String(init?.body))).toMatchObject({
      action_type: 'FOLLOW_UP',
      related_event_ids: ['synthetic-event'],
      assignee_actor_id: null,
    });
  });

  it('updates status with the action version and never accepts a caller-selected owner', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success(coreAction('COMPLETED', 2)),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await updateCareAction(config, 'synthetic-elder', action, {
      status: 'COMPLETED',
      resolution: 'Completed with the elder',
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/care-actions/synthetic-action');
    expect(init?.method).toBe('PATCH');
    expect(new Headers(init?.headers).get('Idempotency-Key')).toMatch('care-action-update-');
    expect(JSON.parse(String(init?.body))).toEqual({
      status: 'COMPLETED',
      expected_version: 1,
      resolution: 'Completed with the elder',
      due_at: null,
    });
    expect(result.status).toBe('COMPLETED');
    expect(result.version).toBe(2);
  });
});
