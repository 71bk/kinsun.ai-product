import { apiFetch, type ApiConfig } from './client';

export type PrimaryCareSetting = 'DAYCARE' | 'COMMUNITY' | 'HOME_CARE' | 'INDEPENDENT';
export type ElderServiceStatus = 'ACTIVE' | 'INACTIVE' | 'DECEASED' | 'DELETED';

interface CoreElderSummary {
  elder_id: string;
  display_name: string;
  primary_care_setting: PrimaryCareSetting;
  status: ElderServiceStatus;
}

interface CoreElderAccessContext {
  purpose: string;
  allowed_actions: string[];
  source_type: 'relationship' | 'assignment' | null;
  source_summary: string;
  expires_at: string | null;
}

export interface ElderWorkspaceView {
  elderId: string;
  displayName: string;
  primaryCareSetting: PrimaryCareSetting;
  status: ElderServiceStatus;
  purpose: string;
  allowedActions: string[];
  sourceType: CoreElderAccessContext['source_type'];
  sourceSummary: string;
  expiresAt: string | null;
}

/**
 * Reads identity and current authorization together. Callers must not render
 * elder identity until this whole promise resolves: either request may return
 * the same non-disclosing 404 for absent and unauthorized resources.
 */
export async function getElderWorkspace(
  config: ApiConfig,
  elderId: string,
): Promise<ElderWorkspaceView> {
  const [elder, access] = await Promise.all([
    apiFetch<CoreElderSummary>(config, `/api/v1/elders/${elderId}`),
    apiFetch<CoreElderAccessContext>(config, `/api/v1/elders/${elderId}/access-context`),
  ]);

  return {
    elderId: elder.elder_id,
    displayName: elder.display_name,
    primaryCareSetting: elder.primary_care_setting,
    status: elder.status,
    purpose: access.purpose,
    allowedActions: access.allowed_actions,
    sourceType: access.source_type,
    sourceSummary: access.source_summary,
    expiresAt: access.expires_at,
  };
}
