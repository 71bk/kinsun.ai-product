import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import {
  completeAssignment,
  listAssignments,
  startAssignment,
  type AssignmentView,
} from './assignments';

const config: ApiConfig = { apiBaseUrl: '/backend/core' };

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

function coreAssignment(status = 'CONFIRMED', version = 3) {
  return {
    assignment_id: 'synthetic-assignment',
    elder_id: 'synthetic-elder',
    provider_tenant_id: 'synthetic-tenant',
    care_unit_id: 'synthetic-unit',
    home_care_worker_id: 'synthetic-worker',
    scheduled_start: '2026-08-13T01:00:00Z',
    scheduled_end: '2026-08-13T02:00:00Z',
    status,
    allowed_data_scopes: ['elder:basic:read', 'care_event:read'],
    version,
    expires_at: '2026-08-13T02:00:00Z',
  };
}

const assignment: AssignmentView = {
  assignmentId: 'synthetic-assignment',
  elderId: 'synthetic-elder',
  scheduledStart: '2026-08-13T01:00:00Z',
  scheduledEnd: '2026-08-13T02:00:00Z',
  status: 'CONFIRMED',
  scopeCount: 2,
  version: 3,
  expiresAt: '2026-08-13T02:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('assignment API boundary', () => {
  it('sends the selected date to Core and exposes only the limited UI view', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success({ items: [coreAssignment()] }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await listAssignments(config, '2026-08-13');

    expect(String(fetchMock.mock.calls[0][0])).toContain('date=2026-08-13');
    expect(result[0]).toEqual(assignment);
    expect(result[0]).not.toHaveProperty('providerTenantId');
    expect(result[0]).not.toHaveProperty('allowedDataScopes');
  });

  it.each([
    ['start', startAssignment, 'WORKER_STARTED_VISIT'],
    ['complete', completeAssignment, 'WORKER_COMPLETED_VISIT'],
  ] as const)('keeps %s idempotent and version-checked', async (command, execute, reasonCode) => {
    const nextStatus = command === 'start' ? 'IN_PROGRESS' : 'COMPLETED';
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      success(coreAssignment(nextStatus, 4)),
    );
    vi.stubGlobal('fetch', fetchMock);

    await execute(config, assignment);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(`/synthetic-assignment/${command}`);
    expect(new Headers(init?.headers).get('Idempotency-Key')).toMatch(`assignment-${command}-`);
    expect(JSON.parse(String(init?.body))).toEqual({
      expected_version: 3,
      reason_code: reasonCode,
    });
  });
});
