import { apiFetch, type ApiConfig } from './client';

export interface LineLinkStatus {
  provider: 'LINE';
  linked: boolean;
  status: 'ACTIVE' | 'UNLINKED';
  linked_at: string | null;
  can_unlink: boolean;
}

export function getLineLinkStatus(config: ApiConfig): Promise<LineLinkStatus> {
  return apiFetch<LineLinkStatus>(config, '/api/v1/me/line-link');
}

export function unlinkLineAccount(config: ApiConfig): Promise<LineLinkStatus> {
  return apiFetch<LineLinkStatus>(config, '/api/v1/me/line-link', { method: 'DELETE' });
}
