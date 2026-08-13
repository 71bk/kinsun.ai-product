import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type AssignmentStatus =
  'DRAFT' | 'CONFIRMED' | 'IN_PROGRESS' | 'COMPLETED' | 'EXPIRED' | 'CANCELLED' | 'NO_SHOW';

interface CoreAssignment {
  assignment_id: string;
  elder_id: string;
  provider_tenant_id: string;
  care_unit_id: string;
  home_care_worker_id: string;
  scheduled_start: string;
  scheduled_end: string;
  status: AssignmentStatus;
  allowed_data_scopes: string[];
  version: number;
  expires_at: string;
}

interface CoreAssignmentList {
  items: CoreAssignment[];
}

export interface AssignmentView {
  assignmentId: string;
  elderId: string;
  scheduledStart: string;
  scheduledEnd: string;
  status: AssignmentStatus;
  scopeCount: number;
  version: number;
  expiresAt: string;
}

function toAssignmentView(assignment: CoreAssignment): AssignmentView {
  return {
    assignmentId: assignment.assignment_id,
    elderId: assignment.elder_id,
    scheduledStart: assignment.scheduled_start,
    scheduledEnd: assignment.scheduled_end,
    status: assignment.status,
    scopeCount: assignment.allowed_data_scopes.length,
    version: assignment.version,
    expiresAt: assignment.expires_at,
  };
}

export async function listAssignments(config: ApiConfig, date: string): Promise<AssignmentView[]> {
  const result = await apiFetch<CoreAssignmentList>(
    config,
    `/api/v1/home-care/assignments?date=${encodeURIComponent(date)}`,
  );
  return result.items.map(toAssignmentView);
}

async function commandAssignment(
  config: ApiConfig,
  assignment: AssignmentView,
  command: 'start' | 'complete',
): Promise<AssignmentView> {
  const result = await apiFetch<CoreAssignment>(
    config,
    `/api/v1/home-care/assignments/${assignment.assignmentId}/${command}`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey(`assignment-${command}`) },
      body: JSON.stringify({
        expected_version: assignment.version,
        reason_code: command === 'start' ? 'WORKER_STARTED_VISIT' : 'WORKER_COMPLETED_VISIT',
      }),
    },
  );
  return toAssignmentView(result);
}

export function startAssignment(
  config: ApiConfig,
  assignment: AssignmentView,
): Promise<AssignmentView> {
  return commandAssignment(config, assignment, 'start');
}

export function completeAssignment(
  config: ApiConfig,
  assignment: AssignmentView,
): Promise<AssignmentView> {
  return commandAssignment(config, assignment, 'complete');
}
