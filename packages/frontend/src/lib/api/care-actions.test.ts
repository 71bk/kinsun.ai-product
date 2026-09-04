import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import {
  adoptCareActionCandidate,
  createCareAction,
  dismissCareActionCandidate,
  listCareActionCandidates,
  listCareActions,
  updateCareAction,
  type CareActionCandidateView,
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

function coreCandidate(status = 'PENDING_REVIEW', version = 1) {
  return {
    care_action_candidate_id: 'synthetic-candidate',
    elder_id: 'synthetic-elder',
    action_type: 'CONTACT_FAMILY',
    suggested_title: 'Confirm the missed contact',
    trigger_reason: 'A reviewed missed-contact event needs follow-up',
    source_event_provenance: coreAction().source_event_provenance,
    suggested_due_at: '2026-09-05T01:00:00Z',
    priority: 'MEDIUM',
    status,
    disposition_reason_code: status === 'PENDING_REVIEW' ? null : 'HUMAN_CONFIRMED',
    disposition_notes: null,
    decided_by_actor_id: status === 'PENDING_REVIEW' ? null : 'synthetic-worker',
    decided_at: status === 'PENDING_REVIEW' ? null : '2026-09-04T02:00:00Z',
    adopted_care_action_id: status === 'ADOPTED' ? 'synthetic-action' : null,
    extractor_version: 'care-action-candidate-v1',
    version,
    created_at: '2026-09-04T01:00:00Z',
    updated_at: '2026-09-04T01:00:00Z',
  };
}

const candidate: CareActionCandidateView = {
  careActionCandidateId: 'synthetic-candidate',
  elderId: 'synthetic-elder',
  actionType: 'CONTACT_FAMILY',
  suggestedTitle: 'Confirm the missed contact',
  triggerReason: 'A reviewed missed-contact event needs follow-up',
  sourceEventProvenance: action.sourceEventProvenance,
  suggestedDueAt: '2026-09-05T01:00:00Z',
  priority: 'MEDIUM',
  status: 'PENDING_REVIEW',
  dispositionReasonCode: null,
  dispositionNotes: null,
  decidedByActorId: null,
  decidedAt: null,
  adoptedCareActionId: null,
  extractorVersion: 'care-action-candidate-v1',
  version: 1,
  createdAt: '2026-09-04T01:00:00Z',
  updatedAt: '2026-09-04T01:00:00Z',
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

    const result = await listCareActions(config, 'synthetic-elder', {
      statuses: ['OPEN', 'IN_PROGRESS'],
      cursor: 'opaque-current',
    });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('status=OPEN');
    expect(url).toContain('status=IN_PROGRESS');
    expect(url).toContain('cursor=opaque-current');
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

  it('lists pending AI candidates separately from formal actions', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success({ items: [coreCandidate()], next_cursor: 'candidate-next', has_more: true }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await listCareActionCandidates(config, 'synthetic-elder');

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/care-action-candidates?');
    expect(url).not.toContain('/care-actions?');
    expect(result).toEqual({ items: [candidate], nextCursor: 'candidate-next', hasMore: true });
  });

  it('adopts with the candidate version and no caller-controlled source ids', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success(coreCandidate('ADOPTED', 2)),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await adoptCareActionCandidate(config, 'synthetic-elder', candidate);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/care-action-candidates/synthetic-candidate/adopt');
    expect(new Headers(init?.headers).get('Idempotency-Key')).toMatch(
      'care-action-candidate-adopt-',
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      expected_version: 1,
      title: null,
      due_at: null,
      priority: null,
    });
    expect(String(init?.body)).not.toContain('source_event');
    expect(result.status).toBe('ADOPTED');
  });

  it('rejects or excludes with a mandatory auditable reason', async () => {
    const rejected = {
      ...coreCandidate('REJECTED', 2),
      disposition_reason_code: 'NOT_NEEDED',
      adopted_care_action_id: null,
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success(rejected),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await dismissCareActionCandidate(config, 'synthetic-elder', candidate, {
      decision: 'REJECT',
      reasonCode: 'NOT_NEEDED',
      notes: 'Already contacted',
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/care-action-candidates/synthetic-candidate/dismiss');
    expect(new Headers(init?.headers).get('Idempotency-Key')).toMatch(
      'care-action-candidate-dismiss-',
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      decision: 'REJECT',
      expected_version: 1,
      reason_code: 'NOT_NEEDED',
      notes: 'Already contacted',
    });
    expect(result.status).toBe('REJECTED');
    expect(result.adoptedCareActionId).toBeNull();
  });
});
