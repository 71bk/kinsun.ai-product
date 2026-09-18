import { ApiRequestError, apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type StaffRole = 'DAYCARE_CARE_WORKER' | 'HOME_CARE_WORKER';
export type CareUnitType = 'DAYCARE_CENTER' | 'COMMUNITY_SITE' | 'HOME_CARE_AGENCY';
export type InvitationStatus = 'ISSUED' | 'ACCEPTED' | 'REVOKED' | 'EXPIRED';

/**
 * Core rejects a role/unit pair it does not recognise with the same opaque 404
 * it uses for "no such unit", so the form filters the picker instead of letting
 * the administrator discover the rule through a failure. Mirrors ROLE_UNITS in
 * `services/core-api/app/services/staff_invitation_service.py` — keep both sides
 * in step when a new unit type or workforce role is added.
 */
export const ROLE_UNIT_TYPES: Record<StaffRole, readonly CareUnitType[]> = {
  DAYCARE_CARE_WORKER: ['DAYCARE_CENTER', 'COMMUNITY_SITE'],
  HOME_CARE_WORKER: ['HOME_CARE_AGENCY'],
};

interface CareUnitWire {
  care_unit_id: string;
  name: string;
  unit_type: CareUnitType;
}
interface InvitationWire {
  invitation_id: string;
  display_name: string;
  role_code: StaffRole;
  care_unit_id: string;
  status: InvitationStatus;
  expires_at: string;
  version: number;
}
interface CreatedInvitationWire extends InvitationWire {
  invitation_token: string;
}
interface ListWire<T> {
  items: T[];
  next_cursor: string | null;
}

export interface CareUnit {
  careUnitId: string;
  name: string;
  unitType: CareUnitType;
}
export interface StaffInvitation {
  invitationId: string;
  displayName: string;
  roleCode: StaffRole;
  careUnitId: string;
  status: InvitationStatus;
  expiresAt: string;
  version: number;
}
export interface IssuedStaffInvitation extends StaffInvitation {
  /** Returned by Core exactly once and stored only as a SHA-256 digest (ADR 0024). */
  invitationToken: string;
}
export interface Page<T> {
  items: T[];
  nextCursor: string | null;
}

/**
 * Every failure Core can produce here, reduced to what the UI may honestly claim.
 *
 * Two collapses are deliberate, not laziness:
 *
 * `unavailable` — Core answers "not an administrator", "feature switched off",
 * "no such care unit" and "role does not match this unit type" with the same
 * opaque 404. Repeating the server's message, or guessing between them, would
 * leak exactly the distinction Core went out of its way to hide (AGENTS.md §4).
 *
 * `conflict` — `ConflictError` and `OptimisticConcurrencyError` both map to
 * `VERSION_OR_IDEMPOTENCY_CONFLICT` in `app/api/error_handlers.py`, so a 409
 * cannot be resolved into "that email already has an account" versus "this
 * request was already submitted" versus "someone else changed this row". The
 * caller phrases it for its own operation; neither may assert a single cause.
 */
export type InvitationFailure = 'unavailable' | 'conflict' | 'network';

export function invitationFailure(error: unknown): InvitationFailure {
  if (!(error instanceof ApiRequestError)) return 'network';
  if (error.status === 409) return 'conflict';
  if (error.status === 404) return 'unavailable';
  return error.retryable ? 'network' : 'unavailable';
}

function careUnit(wire: CareUnitWire): CareUnit {
  return { careUnitId: wire.care_unit_id, name: wire.name, unitType: wire.unit_type };
}

function invitation(wire: InvitationWire): StaffInvitation {
  return {
    invitationId: wire.invitation_id,
    displayName: wire.display_name,
    roleCode: wire.role_code,
    careUnitId: wire.care_unit_id,
    status: wire.status,
    expiresAt: wire.expires_at,
    version: wire.version,
  };
}

export async function listCareUnits(config: ApiConfig): Promise<Page<CareUnit>> {
  const wire = await apiFetch<ListWire<CareUnitWire>>(config, '/api/v1/admin/care-units?limit=100');
  return { items: wire.items.map(careUnit), nextCursor: wire.next_cursor };
}

export async function listStaffInvitations(config: ApiConfig): Promise<Page<StaffInvitation>> {
  const wire = await apiFetch<ListWire<InvitationWire>>(
    config,
    '/api/v1/admin/staff-invitations?limit=100',
  );
  return { items: wire.items.map(invitation), nextCursor: wire.next_cursor };
}

export interface CreateStaffInvitationInput {
  email: string;
  displayName: string;
  roleCode: StaffRole;
  careUnitId: string;
}

/**
 * A fresh idempotency key per attempt is deliberate. Core treats a replayed key
 * as a conflict rather than returning the stored receipt, because the credential
 * it would have to replay no longer exists anywhere — retrying under the same
 * key could only ever produce an invitation whose link nobody can read.
 */
export async function createStaffInvitation(
  config: ApiConfig,
  input: CreateStaffInvitationInput,
): Promise<IssuedStaffInvitation> {
  const wire = await apiFetch<CreatedInvitationWire>(config, '/api/v1/admin/staff-invitations', {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('staff-invitation') },
    body: JSON.stringify({
      email: input.email,
      display_name: input.displayName,
      role_code: input.roleCode,
      care_unit_id: input.careUnitId,
    }),
  });
  return { ...invitation(wire), invitationToken: wire.invitation_token };
}

export async function revokeStaffInvitation(
  config: ApiConfig,
  invitationId: string,
  expectedVersion: number,
): Promise<StaffInvitation> {
  const wire = await apiFetch<InvitationWire>(
    config,
    `/api/v1/admin/staff-invitations/${encodeURIComponent(invitationId)}/revoke`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('staff-invitation-revoke') },
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
  );
  return invitation(wire);
}
