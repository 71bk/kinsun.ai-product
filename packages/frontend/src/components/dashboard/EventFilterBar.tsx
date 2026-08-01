'use client';

import type { EventType, ReviewStatus } from '@elderly-care/shared';
import type { ListEventsFilters } from '@/lib/api/events';

export interface EventFilterBarProps {
  filters: ListEventsFilters;
  onChange: (filters: ListEventsFilters) => void;
}

const EVENT_TYPES: EventType[] = ['meal', 'activity', 'sleep', 'medication_statement', 'emotion', 'important_event'];
const REVIEW_STATUSES: ReviewStatus[] = ['auto_approved', 'needs_review', 'caregiver_confirmed', 'caregiver_rejected'];

/** Date-range / type / review-status filtering for the event timeline (B04.1). */
export function EventFilterBar({ filters, onChange }: EventFilterBarProps) {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
      <label>
        起始日期{' '}
        <input
          type="date"
          value={filters.dateFrom ?? ''}
          onChange={(e) => onChange({ ...filters, dateFrom: e.target.value || undefined })}
        />
      </label>
      <label>
        結束日期{' '}
        <input
          type="date"
          value={filters.dateTo ?? ''}
          onChange={(e) => onChange({ ...filters, dateTo: e.target.value || undefined })}
        />
      </label>
      <label>
        類型{' '}
        <select
          value={filters.eventType ?? ''}
          onChange={(e) => onChange({ ...filters, eventType: (e.target.value || undefined) as EventType | undefined })}
        >
          <option value="">全部</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label>
        審查狀態{' '}
        <select
          value={filters.reviewStatus ?? ''}
          onChange={(e) => onChange({ ...filters, reviewStatus: (e.target.value || undefined) as ReviewStatus | undefined })}
        >
          <option value="">全部</option>
          {REVIEW_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
