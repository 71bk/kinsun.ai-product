import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type ConsentPurpose =
  | 'BASIC_VOICE'
  | 'TRANSCRIPT_STORAGE'
  | 'CARE_EVENT_EXTRACTION'
  | 'LONG_TERM_MEMORY'
  | 'COMPANION_SIGNAL_ANALYSIS'
  | 'PROACTIVE_COMPANION'
  | 'FAMILY_SHARING';

export interface ConsentRecord {
  consent_id: string;
  purpose_code: ConsentPurpose;
  consent_version: number;
  status: 'PENDING' | 'GRANTED' | 'REVOKED' | 'EXPIRED' | 'REJECTED';
  policy_version: string;
  effective_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  affected_capabilities: string[];
  deletion_request_id: string | null;
}

interface ConsentList {
  items: ConsentRecord[];
}

export type ConsentApiConfig = ApiConfig;

export async function listConsents(config: ApiConfig, elderId: string): Promise<ConsentRecord[]> {
  const result = await apiFetch<ConsentList>(config, `/api/v1/elders/${elderId}/consents`);
  return result.items;
}

export function activeConsentForPurpose(
  items: ConsentRecord[],
  purpose: ConsentPurpose,
): ConsentRecord | null {
  return items.find((item) => item.purpose_code === purpose && item.status === 'GRANTED') ?? null;
}

export function activeBasicVoiceConsent(items: ConsentRecord[]): ConsentRecord | null {
  return activeConsentForPurpose(items, 'BASIC_VOICE');
}

export function activeLongTermMemoryConsent(items: ConsentRecord[]): ConsentRecord | null {
  return activeConsentForPurpose(items, 'LONG_TERM_MEMORY');
}

export function activeFamilySharingConsent(items: ConsentRecord[]): ConsentRecord | null {
  return activeConsentForPurpose(items, 'FAMILY_SHARING');
}

async function grantConsentPurpose(
  config: ApiConfig,
  elderId: string,
  policyVersion: string,
  purpose: ConsentPurpose,
  shareScopes: string[] = [],
): Promise<ConsentRecord> {
  const result = await apiFetch<ConsentList>(config, `/api/v1/elders/${elderId}/consents`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey(`consent-${purpose.toLowerCase()}`) },
    body: JSON.stringify({
      purposes: [purpose],
      share_scopes: shareScopes,
      actor_confirmation: true,
      policy_version: policyVersion,
    }),
  });
  const consent = activeConsentForPurpose(result.items, purpose);
  if (!consent) throw new Error(`CORE_CONSENT_RESPONSE_MISSING_${purpose}`);
  return consent;
}

export async function grantBasicVoiceConsent(
  config: ApiConfig,
  elderId: string,
  policyVersion: string,
): Promise<ConsentRecord> {
  return grantConsentPurpose(config, elderId, policyVersion, 'BASIC_VOICE');
}

export function grantLongTermMemoryConsent(
  config: ApiConfig,
  elderId: string,
  policyVersion: string,
): Promise<ConsentRecord> {
  return grantConsentPurpose(config, elderId, policyVersion, 'LONG_TERM_MEMORY');
}

export function revokeLongTermMemoryConsent(
  config: ApiConfig,
  elderId: string,
  consentId: string,
): Promise<ConsentRecord> {
  return apiFetch(config, `/api/v1/elders/${elderId}/consents/${consentId}/revoke`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('long-term-memory-revoke') },
    body: JSON.stringify({
      reason_code: 'ELDER_REQUESTED_LONG_TERM_MEMORY_STOP',
      revoke_scope: [],
      request_deletion: false,
    }),
  });
}

export function revokeBasicVoiceConsent(
  config: ApiConfig,
  elderId: string,
  consentId: string,
): Promise<ConsentRecord> {
  return apiFetch(config, `/api/v1/elders/${elderId}/consents/${consentId}/revoke`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('consent-revoke') },
    body: JSON.stringify({
      reason_code: 'ELDER_REQUESTED_STOP',
      revoke_scope: [],
      request_deletion: false,
    }),
  });
}

export async function grantFamilySharingConsent(
  config: ApiConfig,
  elderId: string,
  policyVersion: string,
): Promise<ConsentRecord> {
  return grantConsentPurpose(config, elderId, policyVersion, 'FAMILY_SHARING', [
    'REPORT_DAILY',
    'REPORT_WEEKLY',
    'REPORT_MONTHLY',
  ]);
}

export function revokeFamilySharingConsent(
  config: ApiConfig,
  elderId: string,
  consentId: string,
): Promise<ConsentRecord> {
  return apiFetch(config, `/api/v1/elders/${elderId}/consents/${consentId}/revoke`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('family-sharing-revoke') },
    body: JSON.stringify({
      reason_code: 'ELDER_REQUESTED_FAMILY_SHARING_STOP',
      revoke_scope: [],
      request_deletion: false,
    }),
  });
}
