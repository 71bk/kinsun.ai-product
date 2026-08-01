import type { EventType, ListEventsResponse, ReviewStatus, UpdateEventRequest } from '@elderly-care/shared';
import { apiFetch, type ApiConfig } from './client';

export interface ListEventsFilters {
  dateFrom?: string;
  dateTo?: string;
  eventType?: EventType;
  reviewStatus?: ReviewStatus;
  cursor?: string;
}

/** GET /v1/elders/{elderId}/events — supports date range, type, and review-status filters (B04.1). */
export function listEvents(config: ApiConfig, elderId: string, filters: ListEventsFilters = {}): Promise<ListEventsResponse> {
  const params = new URLSearchParams();
  if (filters.dateFrom) params.set('dateFrom', filters.dateFrom);
  if (filters.dateTo) params.set('dateTo', filters.dateTo);
  if (filters.eventType) params.set('eventType', filters.eventType);
  if (filters.reviewStatus) params.set('reviewStatus', filters.reviewStatus);
  if (filters.cursor) params.set('cursor', filters.cursor);
  const query = params.toString();
  return apiFetch<ListEventsResponse>(config, `/v1/elders/${elderId}/events${query ? `?${query}` : ''}`);
}

/** PUT /v1/events/{eventId} — caregiver correction; server records the before/after diff (B03.1, B03.2). */
export function updateEvent(config: ApiConfig, eventId: string, updates: UpdateEventRequest): Promise<void> {
  return apiFetch<void>(config, `/v1/events/${eventId}`, { method: 'PUT', body: JSON.stringify(updates) });
}
