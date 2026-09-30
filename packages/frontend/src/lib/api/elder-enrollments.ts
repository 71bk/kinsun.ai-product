import { apiFetch, type ApiConfig } from './client';
import type { ProfilePage } from './elder-profiles';

export type EnrollmentStatus = 'PENDING' | 'ACTIVE' | 'SUSPENDED' | 'ENDED';
export type EnrollmentAction = 'suspend' | 'resume' | 'end';
export interface Enrollment {
  enrollment_id: string;
  elder_id: string;
  display_name: string;
  care_unit_id: string;
  status: EnrollmentStatus;
  version: number;
  valid_from: string;
  valid_until: string | null;
  ended_at: string | null;
  can_manage: boolean;
}
export interface EnrollmentChange {
  enrollment_change_id: string;
  changed_by_actor_id: string;
  changed_by_name: string;
  from_status: EnrollmentStatus;
  to_status: EnrollmentStatus;
  version: number;
  reason: string;
  created_at: string;
}
const base = '/api/v1/elder-enrollments';
const path = (id: string) => `${base}/${encodeURIComponent(id)}`;
const query = (cursor?: string | null) => cursor ? `?limit=25&cursor=${encodeURIComponent(cursor)}` : '?limit=25';
export const listEnrollments = (config: ApiConfig, cursor?: string | null) =>
  apiFetch<ProfilePage<Enrollment>>(config, base + query(cursor));
export const getEnrollment = (config: ApiConfig, id: string) => apiFetch<Enrollment>(config, path(id));
export const listEnrollmentHistory = (config: ApiConfig, id: string, cursor?: string | null) =>
  apiFetch<ProfilePage<EnrollmentChange>>(config, path(id) + '/history' + query(cursor));
export const changeEnrollment = (config: ApiConfig, id: string, action: EnrollmentAction,
  body: { expected_version: number; reason: string }, key: string) =>
  apiFetch<Enrollment>(config, `${path(id)}/${action}`, {
    method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(body),
  });
