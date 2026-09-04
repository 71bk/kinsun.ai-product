import type { CareActionCandidateView, CareActionView } from '@/lib/api/care-actions';
import type { EventView } from '@/lib/api/events';

function appendUniqueById<T>(current: T[], incoming: T[], idFor: (item: T) => string): T[] {
  const merged = new Map(current.map((item) => [idFor(item), item]));
  for (const item of incoming) merged.set(idFor(item), item);
  return [...merged.values()];
}

/** Append an opaque-cursor page without duplicating a boundary item. */
export function appendCareActionPage(
  current: CareActionView[],
  incoming: CareActionView[],
): CareActionView[] {
  return appendUniqueById(current, incoming, (item) => item.careActionId);
}

/** Append a pending-candidate page without duplicating an opaque cursor boundary. */
export function appendCareActionCandidatePage(
  current: CareActionCandidateView[],
  incoming: CareActionCandidateView[],
): CareActionCandidateView[] {
  return appendUniqueById(current, incoming, (item) => item.careActionCandidateId);
}

/** Merge VERIFIED and CORRECTED source streams into one stable selector list. */
export function mergeFormalEventPages(current: EventView[], incoming: EventView[]): EventView[] {
  return appendUniqueById(current, incoming, (item) => item.eventId).sort((left, right) => {
    const dateOrder = right.eventDate.localeCompare(left.eventDate);
    return dateOrder || right.eventId.localeCompare(left.eventId);
  });
}
