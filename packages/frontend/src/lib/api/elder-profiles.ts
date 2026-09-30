import { apiFetch, type ApiConfig } from './client';
import type { CareProfileCategory } from './assisted-elders';

export type ProfileLanguage = 'ZH_TW' | 'NAN_TW' | 'HAK_TW' | 'EN_US' | 'MIXED' | 'UNKNOWN';
export interface ElderProfile {
  elder_id: string;
  display_name: string;
  preferred_name: string | null;
  preferred_language: ProfileLanguage;
  profile_version: number;
}
export interface CareProfileEntry {
  care_profile_entry_id: string;
  elder_id: string;
  category: CareProfileCategory;
  content: string;
  source_type:
    'STAFF_RECORDED' | 'ELDER_REPORTED' | 'LEGAL_REPRESENTATIVE_REPORTED' | 'CLINICAL_DOCUMENT';
  source_actor_id: string;
  verification_status: 'RECORDED' | 'VERIFIED' | 'DISPUTED' | 'RETIRED';
  effective_from: string;
  retired_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}
export interface ProfileChange {
  profile_change_id: string;
  elder_id: string;
  care_profile_entry_id: string | null;
  changed_by_actor_id: string;
  changed_by_name: string;
  change_type: 'BASIC_UPDATED' | 'CARE_ENTRY_CREATED' | 'CARE_ENTRY_UPDATED' | 'CARE_ENTRY_RETIRED';
  resource_version: number;
  reason: string;
  before_data: ElderProfile | CareProfileEntry | null;
  after_data: ElderProfile | CareProfileEntry;
  created_at: string;
}
export interface ProfilePage<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}
export interface UpdateBasicProfile extends Omit<ElderProfile, 'elder_id' | 'profile_version'> {
  expected_version: number;
  reason: string;
}
export interface CareProfileInput {
  category: CareProfileCategory;
  content: string;
  reason: string;
}

const base = (elderId: string) => `/api/v1/elders/${encodeURIComponent(elderId)}`;
export const getElderProfile = (config: ApiConfig, elderId: string) =>
  apiFetch<ElderProfile>(config, `${base(elderId)}/profile`);
export function listCareProfile(
  config: ApiConfig,
  elderId: string,
  includeRetired: boolean,
  cursor?: string | null,
) {
  const query = new URLSearchParams({ include_retired: String(includeRetired), limit: '50' });
  if (cursor) query.set('cursor', cursor);
  return apiFetch<ProfilePage<CareProfileEntry>>(config, `${base(elderId)}/care-profile?${query}`);
}
export function listProfileHistory(config: ApiConfig, elderId: string, cursor?: string | null) {
  const query = new URLSearchParams({ limit: '25' });
  if (cursor) query.set('cursor', cursor);
  return apiFetch<ProfilePage<ProfileChange>>(config, `${base(elderId)}/profile-history?${query}`);
}
function command<T>(config: ApiConfig, path: string, method: string, body: unknown, key: string) {
  return apiFetch<T>(config, path, {
    method,
    headers: { 'Idempotency-Key': key },
    body: JSON.stringify(body),
  });
}
export const updateElderProfile = (
  config: ApiConfig,
  elderId: string,
  body: UpdateBasicProfile,
  key: string,
) => command<ElderProfile>(config, `${base(elderId)}/profile`, 'PATCH', body, key);
export const createCareProfile = (
  config: ApiConfig,
  elderId: string,
  body: CareProfileInput,
  key: string,
) => command<CareProfileEntry>(config, `${base(elderId)}/care-profile`, 'POST', body, key);
export const updateCareProfile = (
  config: ApiConfig,
  elderId: string,
  entryId: string,
  body: CareProfileInput & { expected_version: number },
  key: string,
) =>
  command<CareProfileEntry>(
    config,
    `${base(elderId)}/care-profile/${encodeURIComponent(entryId)}`,
    'PATCH',
    body,
    key,
  );
export const retireCareProfile = (
  config: ApiConfig,
  elderId: string,
  entryId: string,
  body: { expected_version: number; reason: string },
  key: string,
) =>
  command<CareProfileEntry>(
    config,
    `${base(elderId)}/care-profile/${encodeURIComponent(entryId)}/retire`,
    'POST',
    body,
    key,
  );
