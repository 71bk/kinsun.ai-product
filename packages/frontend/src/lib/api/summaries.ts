import type { SummaryRecord } from '@elderly-care/shared';
import { apiFetch, type ApiConfig } from './client';

/** GET /v1/elders/{elderId}/summaries (B02.3, C02.1) */
export function listSummaries(
  config: ApiConfig,
  elderId: string,
  range?: { dateFrom?: string; dateTo?: string },
): Promise<{ items: SummaryRecord[] }> {
  const params = new URLSearchParams();
  if (range?.dateFrom) params.set('dateFrom', range.dateFrom);
  if (range?.dateTo) params.set('dateTo', range.dateTo);
  const query = params.toString();
  return apiFetch(config, `/v1/elders/${elderId}/summaries${query ? `?${query}` : ''}`);
}

/** PUT /v1/elders/{elderId}/summaries/{date}/publish — makes a summary visible to the family role. */
export function publishSummary(config: ApiConfig, elderId: string, date: string): Promise<SummaryRecord> {
  return apiFetch(config, `/v1/elders/${elderId}/summaries/${date}/publish`, { method: 'PUT' });
}

/** PUT /v1/elders/{elderId}/summaries/{date}/withdraw — hides a published summary from family again. */
export function withdrawSummary(config: ApiConfig, elderId: string, date: string): Promise<SummaryRecord> {
  return apiFetch(config, `/v1/elders/${elderId}/summaries/${date}/withdraw`, { method: 'PUT' });
}
