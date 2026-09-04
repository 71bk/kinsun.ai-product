import { describe, expect, it } from 'vitest';
import type { CareActionView } from '@/lib/api/care-actions';
import type { EventView } from '@/lib/api/events';
import { appendCareActionPage, mergeFormalEventPages } from './care-action-pagination';

function action(id: string, version = 1): CareActionView {
  return {
    careActionId: id,
    elderId: 'synthetic-elder',
    actionType: 'FOLLOW_UP',
    title: `Synthetic action ${id}`,
    description: null,
    triggerReason: 'Synthetic reviewed event',
    relatedEventIds: ['synthetic-event'],
    sourceEventProvenance: [],
    assigneeActorId: 'synthetic-worker',
    dueAt: '2026-09-05T01:00:00Z',
    priority: 'MEDIUM',
    status: 'OPEN',
    resolution: null,
    createdByActorId: 'synthetic-worker',
    version,
    createdAt: '2026-09-04T01:00:00Z',
    updatedAt: '2026-09-04T01:00:00Z',
  };
}

function sourceEvent(id: string, eventDate: string): EventView {
  return {
    eventId: id,
    elderId: 'synthetic-elder',
    eventType: 'MEAL',
    eventDate,
    content: `Synthetic event ${id}`,
    status: 'VERIFIED',
    confidenceBand: 'HIGH',
    evidenceRefs: [],
    version: 1,
    consentVersion: 1,
    structuredPayload: { summary: `Synthetic event ${id}` },
  };
}

describe('Care Action cursor page merging', () => {
  it('keeps every item beyond the first 100 and de-duplicates a page boundary', () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => action(`action-${index + 1}`));
    const merged = appendCareActionPage(firstPage, [action('action-100', 2), action('action-101')]);

    expect(merged).toHaveLength(101);
    expect(merged.at(-1)?.careActionId).toBe('action-101');
    expect(merged.find((item) => item.careActionId === 'action-100')?.version).toBe(2);
  });

  it('merges verified and corrected source pages in stable date order without duplicates', () => {
    const merged = mergeFormalEventPages(
      [sourceEvent('event-a', '2026-09-04'), sourceEvent('event-b', '2026-09-03')],
      [sourceEvent('event-b', '2026-09-03'), sourceEvent('event-c', '2026-09-05')],
    );

    expect(merged.map((item) => item.eventId)).toEqual(['event-c', 'event-a', 'event-b']);
  });

  it('keeps source events beyond the first 100 without duplicating a cursor boundary', () => {
    const firstPage = Array.from({ length: 100 }, (_, index) =>
      sourceEvent(`event-${index + 1}`, '2026-09-04'),
    );
    const merged = mergeFormalEventPages(firstPage, [
      sourceEvent('event-100', '2026-09-04'),
      sourceEvent('event-101', '2026-09-03'),
    ]);

    expect(merged).toHaveLength(101);
    expect(new Set(merged.map((item) => item.eventId)).size).toBe(101);
    expect(merged.some((item) => item.eventId === 'event-101')).toBe(true);
  });
});
