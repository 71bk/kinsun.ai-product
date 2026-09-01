import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type CareProfileCategory =
  | 'HEALTH_CONDITION'
  | 'MEDICATION'
  | 'ALLERGY'
  | 'CARE_PRECAUTION';

export interface CreateAccountlessElderInput {
  organizationId: string;
  careUnitId: string;
  displayName: string;
  preferredName?: string;
  preferredLanguage: 'ZH_TW' | 'NAN_TW' | 'HAK_TW' | 'EN_US' | 'MIXED';
  primaryCareSetting: 'DAYCARE' | 'COMMUNITY';
  careProfile: Array<{ category: CareProfileCategory; content: string }>;
}
export interface AccountlessElderResult {
  elder_id: string;
  actor_id: null;
  enrollment_id: string;
  display_name: string;
  preferred_name: string | null;
}

export interface IssuedAssistedSession {
  assisted_session_id: string;
  elder_id: string;
  pairing_token: string;
  pairing_expires_at: string;
  absolute_expires_at: string;
}

export interface TabletSession {
  assisted_session_id: string;
  elder_id: string;
  display_name: string;
  preferred_name: string | null;
  idle_expires_at: string;
  absolute_expires_at: string;
}

interface CurrentTabletSession extends TabletSession {
  status: 'ACTIVE';
}

export interface AssistedCompanionTurn {
  reply_text: string;
  result_status: 'SUCCESS' | 'BLOCKED' | 'SAFE_FALLBACK' | 'FAILED';
  safety_decision: 'ALLOW' | 'BLOCK' | 'SAFE_FALLBACK' | 'HUMAN_REVIEW';
}

export async function createAccountlessElder(
  config: ApiConfig,
  input: CreateAccountlessElderInput,
): Promise<AccountlessElderResult> {
  return apiFetch(config, `/api/v1/organizations/${input.organizationId}/elders`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('accountless-elder') },
    body: JSON.stringify({
      display_name: input.displayName,
      preferred_name: input.preferredName || null,
      preferred_language: input.preferredLanguage,
      primary_care_setting: input.primaryCareSetting,
      care_unit_id: input.careUnitId,
      response_length_preference: 'STANDARD',
      timezone: 'Asia/Taipei',
      care_profile: input.careProfile,
    }),
  });
}

export function issueAssistedSession(
  config: ApiConfig,
  elderId: string,
): Promise<IssuedAssistedSession> {
  return apiFetch(config, `/api/v1/elders/${elderId}/assisted-sessions`, {
    method: 'POST',
    body: JSON.stringify({ client_timezone: 'Asia/Taipei' }),
  });
}

export async function exchangeTabletPairing(pairingToken: string): Promise<TabletSession> {
  const response = await fetch('/backend/elder-session/exchange', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ pairing_token: pairingToken }),
  });
  if (!response.ok) throw new Error(`PAIRING_${response.status}`);
  return (await response.json()) as TabletSession;
}

export function getCurrentTabletSession(): Promise<CurrentTabletSession> {
  return apiFetch<CurrentTabletSession>(
    { apiBaseUrl: '/backend/elder-session' },
    '/current',
  );
}

export function runAssistedCompanionTurn(inputText: string): Promise<AssistedCompanionTurn> {
  return apiFetch<AssistedCompanionTurn>(
    { apiBaseUrl: '/backend/elder-session' },
    '/companion-turns',
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('elder-turn') },
      body: JSON.stringify({ input_text: inputText }),
    },
  );
}

export async function endTabletSession(): Promise<void> {
  const response = await fetch('/backend/elder-session/current', {
    method: 'DELETE',
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(`END_ELDER_SESSION_${response.status}`);
}
