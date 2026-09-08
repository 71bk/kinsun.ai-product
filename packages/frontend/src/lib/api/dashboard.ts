import { ApiRequestError, apiFetch, type ApiConfig } from './client';

export type ActorRole = 'DAYCARE_CARE_WORKER' | 'HOME_CARE_WORKER' | 'FAMILY_MEMBER' | string;
type ElderMode = 'daycare' | 'home-care' | 'family';

interface ActorProfile {
  role: ActorRole;
  display_name: string;
  tenant_id: string;
  care_unit_ids: string[];
}

interface AuthorizedElderItem {
  elder_id: string;
  display_name: string;
  care_unit_name: string | null;
  authorization_summary: string | null;
  open_care_action_count?: number | null;
  pending_event_review_count?: number | null;
}

interface AuthorizedElderList {
  items: AuthorizedElderItem[];
  page: {
    next_cursor: string | null;
    has_more: boolean;
    limit: number;
  };
}

export interface DashboardElder {
  elderId: string;
  elderName: string;
  careUnitName: string | null;
  authorizationSummary: string | null;
  openCareActionCount: number | null;
  pendingEventReviewCount: number | null;
}

export interface CaregiverDashboard {
  elders: DashboardElder[];
  actorRole: ActorRole;
  actorName: string;
  tenantId: string;
  careUnitIds: string[];
  hasMore: boolean;
}

function modeForRole(role: ActorRole): ElderMode {
  if (role === 'DAYCARE_CARE_WORKER') return 'daycare';
  if (role === 'HOME_CARE_WORKER') return 'home-care';
  if (role === 'FAMILY_MEMBER') return 'family';
  throw new ApiRequestError(403, '目前身分不支援授權長者清單');
}

/**
 * Core derives the actor from authentication. The browser never sends a
 * caregiver ID and only selects the mode allowed by the authenticated role.
 */
export async function getCaregiverDashboard(config: ApiConfig): Promise<CaregiverDashboard> {
  const profile = await apiFetch<ActorProfile>(config, '/api/v1/me');
  const mode = modeForRole(profile.role);
  const result = await apiFetch<AuthorizedElderList>(
    config,
    `/api/v1/me/authorized-elders?mode=${encodeURIComponent(mode)}&limit=100`,
  );

  return {
    actorRole: profile.role,
    actorName: profile.display_name,
    tenantId: profile.tenant_id,
    careUnitIds: profile.care_unit_ids,
    hasMore: result.page.has_more,
    elders: result.items.map((item) => ({
      elderId: item.elder_id,
      elderName: item.display_name,
      careUnitName: item.care_unit_name,
      authorizationSummary: item.authorization_summary,
      pendingEventReviewCount:
        mode !== 'family' &&
        typeof item.pending_event_review_count === 'number' &&
        Number.isSafeInteger(item.pending_event_review_count) &&
        item.pending_event_review_count >= 0
          ? item.pending_event_review_count
          : null,
      openCareActionCount:
        mode !== 'family' &&
        typeof item.open_care_action_count === 'number' &&
        Number.isSafeInteger(item.open_care_action_count) &&
        item.open_care_action_count >= 0
          ? item.open_care_action_count
          : null,
    })),
  };
}
