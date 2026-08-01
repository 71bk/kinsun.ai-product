import type { EventRecord, ReviewStatus } from '@elderly-care/shared';

const RANK: Record<ReviewStatus, number> = {
  caregiver_confirmed: 3,
  auto_approved: 2,
  needs_review: 1,
  caregiver_rejected: 0,
};

/**
 * Orders events for summary generation with caregiver-confirmed data first
 * (B02.2/B03.3) and drops caregiver-rejected events entirely — a rejected
 * event must never influence or be cited by a summary.
 */
export function prioritizeEvents(events: EventRecord[]): EventRecord[] {
  return events
    .filter((e) => e.reviewStatus !== 'caregiver_rejected')
    .slice()
    .sort((a, b) => RANK[b.reviewStatus] - RANK[a.reviewStatus]);
}
