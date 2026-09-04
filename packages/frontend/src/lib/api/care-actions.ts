import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type CareActionType =
  | 'CONTACT_ELDER'
  | 'CONTACT_FAMILY'
  | 'CONFIRM_INFORMATION'
  | 'INVITE_ACTIVITY'
  | 'FOLLOW_UP'
  | 'OTHER';

export type CareActionPriority = 'LOW' | 'MEDIUM' | 'HIGH';
export type CareActionStatus = 'OPEN' | 'IN_PROGRESS' | 'COMPLETED' | 'POSTPONED' | 'CANCELLED';
export type CareActionTransition = Exclude<CareActionStatus, 'OPEN'>;
export type CareActionCandidateStatus = 'PENDING_REVIEW' | 'ADOPTED' | 'REJECTED' | 'EXCLUDED';
export type CareActionCandidateDecision = 'REJECT' | 'EXCLUDE';

interface CoreCareActionSourceEventProvenance {
  event_id: string;
  event_version_id: string;
  event_version: number;
  event_type: string;
  event_time: string | null;
  source_status: 'VERIFIED' | 'CORRECTED';
  snapshot_sha256: string;
  snapshot_schema_version: 'care-event-provenance.v1';
}

interface CoreCareAction {
  care_action_id: string;
  elder_id: string;
  action_type: CareActionType;
  title: string;
  description: string | null;
  trigger_reason: string | null;
  related_event_ids: string[];
  source_event_provenance?: CoreCareActionSourceEventProvenance[];
  assignee_actor_id: string;
  due_at: string | null;
  priority: CareActionPriority;
  status: CareActionStatus;
  resolution: string | null;
  created_by_actor_id: string;
  version: number;
  created_at: string;
  updated_at: string;
}

interface CoreCareActionList {
  items: CoreCareAction[];
  next_cursor: string | null;
  has_more: boolean;
}

interface CoreCareActionCandidate {
  care_action_candidate_id: string;
  elder_id: string;
  action_type: CareActionType;
  suggested_title: string;
  trigger_reason: string;
  source_event_provenance: CoreCareActionSourceEventProvenance[];
  suggested_due_at: string;
  priority: Exclude<CareActionPriority, 'HIGH'>;
  status: CareActionCandidateStatus;
  disposition_reason_code: string | null;
  disposition_notes: string | null;
  decided_by_actor_id: string | null;
  decided_at: string | null;
  adopted_care_action_id: string | null;
  extractor_version: string;
  version: number;
  created_at: string;
  updated_at: string;
}

interface CoreCareActionCandidateList {
  items: CoreCareActionCandidate[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface CareActionView {
  careActionId: string;
  elderId: string;
  actionType: CareActionType;
  title: string;
  description: string | null;
  triggerReason: string | null;
  relatedEventIds: string[];
  sourceEventProvenance: Array<{
    eventId: string;
    eventVersionId: string;
    eventVersion: number;
    eventType: string;
    eventTime: string | null;
    sourceStatus: 'VERIFIED' | 'CORRECTED';
    snapshotSha256: string;
    snapshotSchemaVersion: 'care-event-provenance.v1';
  }>;
  assigneeActorId: string;
  dueAt: string | null;
  priority: CareActionPriority;
  status: CareActionStatus;
  resolution: string | null;
  createdByActorId: string;
  version: number;
  createdAt: string;
  updatedAt: string;
}

export interface CareActionListView {
  items: CareActionView[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface CareActionCandidateView {
  careActionCandidateId: string;
  elderId: string;
  actionType: CareActionType;
  suggestedTitle: string;
  triggerReason: string;
  sourceEventProvenance: CareActionView['sourceEventProvenance'];
  suggestedDueAt: string;
  priority: Exclude<CareActionPriority, 'HIGH'>;
  status: CareActionCandidateStatus;
  dispositionReasonCode: string | null;
  dispositionNotes: string | null;
  decidedByActorId: string | null;
  decidedAt: string | null;
  adoptedCareActionId: string | null;
  extractorVersion: string;
  version: number;
  createdAt: string;
  updatedAt: string;
}

export interface CareActionCandidateListView {
  items: CareActionCandidateView[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface ListCareActionsOptions {
  statuses?: CareActionStatus[];
  cursor?: string;
}

export interface ListCareActionCandidatesOptions {
  statuses?: CareActionCandidateStatus[];
  cursor?: string;
}

export interface CreateCareActionInput {
  actionType: CareActionType;
  title: string;
  description?: string;
  triggerReason: string;
  relatedEventIds: string[];
  dueAt: string;
  priority: CareActionPriority;
}

export interface UpdateCareActionInput {
  status: CareActionTransition;
  resolution?: string;
  dueAt?: string;
}

export interface AdoptCareActionCandidateInput {
  title?: string;
  dueAt?: string;
  priority?: CareActionPriority;
}

export interface DismissCareActionCandidateInput {
  decision: CareActionCandidateDecision;
  reasonCode: string;
  notes?: string;
}

function toSourceEventProvenance(source: CoreCareActionSourceEventProvenance) {
  return {
    eventId: source.event_id,
    eventVersionId: source.event_version_id,
    eventVersion: source.event_version,
    eventType: source.event_type,
    eventTime: source.event_time,
    sourceStatus: source.source_status,
    snapshotSha256: source.snapshot_sha256,
    snapshotSchemaVersion: source.snapshot_schema_version,
  };
}

function toCareActionView(action: CoreCareAction): CareActionView {
  return {
    careActionId: action.care_action_id,
    elderId: action.elder_id,
    actionType: action.action_type,
    title: action.title,
    description: action.description,
    triggerReason: action.trigger_reason,
    relatedEventIds: action.related_event_ids,
    sourceEventProvenance: (action.source_event_provenance ?? []).map(toSourceEventProvenance),
    assigneeActorId: action.assignee_actor_id,
    dueAt: action.due_at,
    priority: action.priority,
    status: action.status,
    resolution: action.resolution,
    createdByActorId: action.created_by_actor_id,
    version: action.version,
    createdAt: action.created_at,
    updatedAt: action.updated_at,
  };
}

function toCareActionCandidateView(candidate: CoreCareActionCandidate): CareActionCandidateView {
  return {
    careActionCandidateId: candidate.care_action_candidate_id,
    elderId: candidate.elder_id,
    actionType: candidate.action_type,
    suggestedTitle: candidate.suggested_title,
    triggerReason: candidate.trigger_reason,
    sourceEventProvenance: candidate.source_event_provenance.map(toSourceEventProvenance),
    suggestedDueAt: candidate.suggested_due_at,
    priority: candidate.priority,
    status: candidate.status,
    dispositionReasonCode: candidate.disposition_reason_code,
    dispositionNotes: candidate.disposition_notes,
    decidedByActorId: candidate.decided_by_actor_id,
    decidedAt: candidate.decided_at,
    adoptedCareActionId: candidate.adopted_care_action_id,
    extractorVersion: candidate.extractor_version,
    version: candidate.version,
    createdAt: candidate.created_at,
    updatedAt: candidate.updated_at,
  };
}

export async function listCareActions(
  config: ApiConfig,
  elderId: string,
  options: ListCareActionsOptions = {},
): Promise<CareActionListView> {
  const params = new URLSearchParams({ limit: '100' });
  for (const status of options.statuses ?? []) params.append('status', status);
  if (options.cursor) params.set('cursor', options.cursor);
  const result = await apiFetch<CoreCareActionList>(
    config,
    `/api/v1/elders/${elderId}/care-actions?${params.toString()}`,
  );
  return {
    items: result.items.map(toCareActionView),
    nextCursor: result.next_cursor,
    hasMore: result.has_more,
  };
}

export async function createCareAction(
  config: ApiConfig,
  elderId: string,
  input: CreateCareActionInput,
): Promise<CareActionView> {
  const result = await apiFetch<CoreCareAction>(config, `/api/v1/elders/${elderId}/care-actions`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('care-action-create') },
    body: JSON.stringify({
      action_type: input.actionType,
      title: input.title,
      description: input.description?.trim() || null,
      trigger_reason: input.triggerReason,
      related_event_ids: input.relatedEventIds,
      assignee_actor_id: null,
      due_at: input.dueAt,
      priority: input.priority,
    }),
  });
  return toCareActionView(result);
}

export async function listCareActionCandidates(
  config: ApiConfig,
  elderId: string,
  options: ListCareActionCandidatesOptions = {},
): Promise<CareActionCandidateListView> {
  const params = new URLSearchParams({ limit: '100' });
  for (const status of options.statuses ?? []) params.append('status', status);
  if (options.cursor) params.set('cursor', options.cursor);
  const result = await apiFetch<CoreCareActionCandidateList>(
    config,
    `/api/v1/elders/${elderId}/care-action-candidates?${params.toString()}`,
  );
  return {
    items: result.items.map(toCareActionCandidateView),
    nextCursor: result.next_cursor,
    hasMore: result.has_more,
  };
}

export async function adoptCareActionCandidate(
  config: ApiConfig,
  elderId: string,
  candidate: CareActionCandidateView,
  input: AdoptCareActionCandidateInput = {},
): Promise<CareActionCandidateView> {
  const result = await apiFetch<CoreCareActionCandidate>(
    config,
    `/api/v1/elders/${elderId}/care-action-candidates/${candidate.careActionCandidateId}/adopt`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('care-action-candidate-adopt') },
      body: JSON.stringify({
        expected_version: candidate.version,
        title: input.title?.trim() || null,
        due_at: input.dueAt ?? null,
        priority: input.priority ?? null,
      }),
    },
  );
  return toCareActionCandidateView(result);
}

export async function dismissCareActionCandidate(
  config: ApiConfig,
  elderId: string,
  candidate: CareActionCandidateView,
  input: DismissCareActionCandidateInput,
): Promise<CareActionCandidateView> {
  const result = await apiFetch<CoreCareActionCandidate>(
    config,
    `/api/v1/elders/${elderId}/care-action-candidates/${candidate.careActionCandidateId}/dismiss`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('care-action-candidate-dismiss') },
      body: JSON.stringify({
        decision: input.decision,
        expected_version: candidate.version,
        reason_code: input.reasonCode,
        notes: input.notes?.trim() || null,
      }),
    },
  );
  return toCareActionCandidateView(result);
}

export async function updateCareAction(
  config: ApiConfig,
  elderId: string,
  action: CareActionView,
  input: UpdateCareActionInput,
): Promise<CareActionView> {
  const result = await apiFetch<CoreCareAction>(
    config,
    `/api/v1/elders/${elderId}/care-actions/${action.careActionId}`,
    {
      method: 'PATCH',
      headers: { 'Idempotency-Key': createIdempotencyKey('care-action-update') },
      body: JSON.stringify({
        status: input.status,
        expected_version: action.version,
        resolution: input.resolution?.trim() || null,
        due_at: input.dueAt ?? null,
      }),
    },
  );
  return toCareActionView(result);
}
