import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { EventRecord, EventType, ReviewStatus, SummaryContent } from '@elderly-care/shared';
import { SummaryGenerator, type SummaryDataStore, type SummaryGenerationAdapter } from './generator.js';

class InMemorySummaryStore implements SummaryDataStore {
  public events: EventRecord[] = [];
  public savedSummary: unknown = null;

  async queryByPk<T>(pk: string, skPrefix?: string): Promise<T[]> {
    return this.events.filter((e) => e.PK === pk && (!skPrefix || e.SK.startsWith(skPrefix))) as unknown as T[];
  }

  async putItem<T extends object>(item: T): Promise<void> {
    this.savedSummary = item;
  }
}

const fakeAdapter: SummaryGenerationAdapter = {
  async generate(): Promise<SummaryContent> {
    return {
      overview: '今日狀況良好',
      meals: ['早餐：地瓜稀飯'],
      activities: ['公園散步'],
      sleep: '睡眠正常',
      medicationStatements: ['有吃血壓藥'],
      importantEvents: [],
      emotionalState: '心情愉快',
    };
  },
};

function eventArb(elderId: string, date: string): fc.Arbitrary<EventRecord> {
  const eventTypeArb = fc.constantFrom<EventType>('meal', 'activity', 'sleep', 'medication_statement', 'emotion', 'important_event');
  const reviewStatusArb = fc.constantFrom<ReviewStatus>('auto_approved', 'needs_review', 'caregiver_confirmed', 'caregiver_rejected');
  return fc.record({
    eventId: fc.uuid(),
    eventType: eventTypeArb,
    reviewStatus: reviewStatusArb,
    content: fc.string({ minLength: 1, maxLength: 50 }),
  }).map(({ eventId, eventType, reviewStatus, content }) => ({
    PK: `ELDER#${elderId}`,
    SK: `EVENT#${date}#${eventId}`,
    GSI1PK: `ELDER#${elderId}#EVENT_TYPE#${eventType}`,
    GSI1SK: date,
    GSI2PK: `ELDER#${elderId}#REVIEW#${reviewStatus}`,
    GSI2SK: `${date}#${eventId}`,
    eventId,
    elderId,
    eventType,
    content,
    originalUtterance: content,
    eventDate: date,
    confidence: 0.9,
    sourceConversationId: 'conv-1',
    reviewStatus,
    reviewHistory: [],
    createdAt: `${date}T00:00:00Z`,
    updatedAt: `${date}T00:00:00Z`,
    ttl: 0,
  }));
}

/**
 * Feature: elderly-care-ai-companion, Property 8: 摘要內容可追溯性.
 * For any set of events and the summary generated from them, every entry in
 * sourceEventIds must correspond to a real event that was actually in the
 * input set — a summary can never cite an event ID that doesn't exist.
 * Caregiver-rejected events must never appear in sourceEventIds either.
 */
describe('Property 8: Summary content traceability', () => {
  it('sourceEventIds is always a subset of the elder\'s actual events for that date', async () => {
    await fc.assert(
      fc.asyncProperty(fc.array(eventArb('elder-1', '2026-07-24'), { minLength: 0, maxLength: 15 }), async (events) => {
        const store = new InMemorySummaryStore();
        store.events = events;
        const generator = new SummaryGenerator(store, fakeAdapter);

        const record = await generator.generateDailySummary('elder-1', '2026-07-24');

        const realEventIds = new Set(events.map((e) => e.eventId));
        for (const sourceId of record.sourceEventIds) {
          expect(realEventIds.has(sourceId)).toBe(true);
        }
      }),
      { numRuns: 100 },
    );
  });

  it('never cites a caregiver_rejected event in sourceEventIds', async () => {
    await fc.assert(
      fc.asyncProperty(fc.array(eventArb('elder-1', '2026-07-24'), { minLength: 1, maxLength: 15 }), async (events) => {
        const store = new InMemorySummaryStore();
        store.events = events;
        const generator = new SummaryGenerator(store, fakeAdapter);

        const record = await generator.generateDailySummary('elder-1', '2026-07-24');

        const rejectedIds = new Set(events.filter((e) => e.reviewStatus === 'caregiver_rejected').map((e) => e.eventId));
        for (const sourceId of record.sourceEventIds) {
          expect(rejectedIds.has(sourceId)).toBe(false);
        }
      }),
      { numRuns: 100 },
    );
  });

  it('the persisted record matches what generateDailySummary returned', async () => {
    const store = new InMemorySummaryStore();
    store.events = [];
    const generator = new SummaryGenerator(store, fakeAdapter);
    const record = await generator.generateDailySummary('elder-1', '2026-07-24');
    expect(store.savedSummary).toEqual(record);
  });
});
