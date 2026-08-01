import type { CaregiverDashboardResponse } from '@elderly-care/shared';
import { apiFetch, type ApiConfig } from './client';

/** GET /v1/caregivers/{caregiverId}/dashboard (C01.1) — server already scopes to elders this caregiver may see. */
export function getCaregiverDashboard(config: ApiConfig, caregiverId: string): Promise<CaregiverDashboardResponse> {
  return apiFetch<CaregiverDashboardResponse>(config, `/v1/caregivers/${caregiverId}/dashboard`);
}
