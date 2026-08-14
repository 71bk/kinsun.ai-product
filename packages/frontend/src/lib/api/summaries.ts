import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';

export type CoreSummaryStatus =
  'DRAFT' | 'READY' | 'NEEDS_REVIEW' | 'PUBLISHED' | 'STALE' | 'WITHDRAWN';

export interface SummaryItemView {
  category: 'MEAL' | 'ACTIVITY' | 'SLEEP' | 'MEDICATION_STATEMENT' | 'SOCIAL' | 'IMPORTANT_EVENT';
  text: string;
  sourceEventIds: string[];
  dataStatus: 'PRESENT' | 'NOT_MENTIONED' | 'INSUFFICIENT';
}

interface CoreSummaryItem {
  category: SummaryItemView['category'];
  text: string;
  source_event_ids: string[];
  data_status: SummaryItemView['dataStatus'];
}

interface CoreSummary {
  summary_id: string;
  elder_id: string;
  summary_date: string;
  summary_type: 'PROFESSIONAL_DAILY';
  status: CoreSummaryStatus;
  items: CoreSummaryItem[];
  missing_fields: string[];
  conflict_flags: string[];
  version: number;
  generated_at: string | null;
  created_at: string;
  updated_at: string;
}

interface CoreSummaryList {
  items: CoreSummary[];
}

export interface SummaryView {
  summaryId: string;
  elderId: string;
  date: string;
  status: CoreSummaryStatus;
  items: SummaryItemView[];
  missingFields: string[];
  conflictFlags: string[];
  version: number;
  generatedAt: string | null;
  updatedAt: string;
}

export interface ListSummaryFilters {
  date?: string;
  statuses?: CoreSummaryStatus[];
}

export type ReviewSummaryDecision = 'VERIFY' | 'REJECT';

function toSummaryView(summary: CoreSummary): SummaryView {
  return {
    summaryId: summary.summary_id,
    elderId: summary.elder_id,
    date: summary.summary_date,
    status: summary.status,
    items: summary.items.map((item) => ({
      category: item.category,
      text: item.text,
      sourceEventIds: item.source_event_ids,
      dataStatus: item.data_status,
    })),
    missingFields: summary.missing_fields,
    conflictFlags: summary.conflict_flags,
    version: summary.version,
    generatedAt: summary.generated_at,
    updatedAt: summary.updated_at,
  };
}

/** Summary publication is not exposed by Core; this client intentionally supports formal reads only. */
export async function listSummaries(
  config: ApiConfig,
  elderId: string,
  filters: ListSummaryFilters = {},
): Promise<{ items: SummaryView[] }> {
  const params = new URLSearchParams();
  if (filters.date) params.set('date', filters.date);
  filters.statuses?.forEach((status) => params.append('status', status));
  const query = params.toString();
  const result = await apiFetch<CoreSummaryList>(
    config,
    `/api/v1/elders/${elderId}/summaries${query ? `?${query}` : ''}`,
  );
  return { items: result.items.map(toSummaryView) };
}

export async function reviewSummary(
  config: ApiConfig,
  elderId: string,
  summary: SummaryView,
  decision: ReviewSummaryDecision,
): Promise<SummaryView> {
  const result = await apiFetch<CoreSummary & { review_record_id: string }>(
    config,
    `/api/v1/elders/${elderId}/summaries/${summary.summaryId}/review`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('summary-review') },
      body: JSON.stringify({
        decision,
        reason_code: 'CAREGIVER_UI_REVIEW',
        expected_version: summary.version,
      }),
    },
  );
  return toSummaryView(result);
}

export async function generateSummary(
  config: ApiConfig,
  elderId: string,
  summaryDate: string,
): Promise<SummaryView> {
  const result = await apiFetch<CoreSummary>(
    config,
    `/api/v1/elders/${elderId}/summaries/generate`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': createIdempotencyKey('summary-generate') },
      body: JSON.stringify({ summary_date: summaryDate }),
    },
  );
  return toSummaryView(result);
}
