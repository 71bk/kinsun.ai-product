import { describe, expect, it } from 'vitest';
import type { ConversationRecord, EventRecord } from '@elderly-care/shared';
import { EventExtractor, type ExtractionAdapter } from '../event-extractor/extractor.js';
import { validateExtractedEvent } from '../event-extractor/schema.js';
import { GSI1, GSI2, Keys, computeTtlEpochSeconds, RETENTION_DAYS } from '../db/index.js';
import { SummaryGenerator, type SummaryDataStore, type SummaryGenerationAdapter } from '../summary/generator.js';

class InMemoryEventStore implements SummaryDataStore {
  public events: EventRecord[] = [];
  public savedSummary: unknown = null;

  async queryByPk<T>(pk: string, skPrefix?: string): Promise<T[]> {
    return this.events.filter((e) => e.PK === pk && (!skPrefix || e.SK.startsWith(skPrefix))) as unknown as T[];
  }

  async putItem<T extends object>(item: T): Promise<void> {
    const record = item as EventRecord | { SK: string };
    if (record.SK.startsWith('EVENT#')) {
      this.events.push(item as EventRecord);
    } else {
      this.savedSummary = item;
    }
  }
}

const conversation: ConversationRecord = {
  PK: 'ELDER#elder-1',
  SK: 'CONV#2026-07-24T00:00:00Z#conv-1',
  conversationId: 'conv-1',
  elderId: 'elder-1',
  startTime: '2026-07-24T00:00:00Z',
  endTime: '2026-07-24T00:05:00Z',
  turns: [
    { role: 'elder', content: '我今天中午吃了地瓜稀飯', timestamp: '2026-07-24T00:00:00Z', language: 'zh-TW' },
    { role: 'elder', content: '早上有去公園散步半小時', timestamp: '2026-07-24T00:01:00Z', language: 'zh-TW' },
  ],
  asrMetadata: null,
  status: 'completed',
  traceId: 'trace-1',
  audioS3Key: null,
  ttl: computeTtlEpochSeconds(RETENTION_DAYS.conversation),
};

const fakeExtractionAdapter: ExtractionAdapter = {
  async extractRaw() {
    const now = '2026-07-24T00:05:00Z';
    return [
      {
        eventId: 'evt-meal-1',
        elderId: 'elder-1',
        eventType: 'meal',
        content: '中午吃了地瓜稀飯',
        originalUtterance: '我今天中午吃了地瓜稀飯',
        eventDate: '2026-07-24',
        confidence: 0.9,
        sourceConversationId: 'conv-1',
        reviewStatus: 'auto_approved',
        createdAt: now,
        metadata: {},
      },
      {
        eventId: 'evt-activity-1',
        elderId: 'elder-1',
        eventType: 'activity',
        content: '早上去公園散步半小時',
        originalUtterance: '早上有去公園散步半小時',
        eventDate: '2026-07-24',
        confidence: 0.85,
        sourceConversationId: 'conv-1',
        reviewStatus: 'auto_approved',
        createdAt: now,
        metadata: {},
      },
    ];
  },
};

const fakeSummaryAdapter: SummaryGenerationAdapter = {
  async generate(_elderId, _date, events) {
    return {
      overview: `今天共有 ${events.length} 筆生活紀錄`,
      meals: events.filter((e) => e.eventType === 'meal').map((e) => e.content),
      activities: events.filter((e) => e.eventType === 'activity').map((e) => e.content),
      sleep: null,
      medicationStatements: [],
      importantEvents: [],
      emotionalState: null,
    };
  },
};

/**
 * 事件擷取與摘要整合測試 (task 25.3). Runs EventExtractor over a fake
 * conversation, persists the validated events into an in-memory store
 * shaped like DynamoDB, then runs SummaryGenerator over that same store —
 * proving the two modules actually agree on the EventRecord shape and that
 * the summary's sourceEventIds trace back to events the extractor
 * genuinely produced (Property 8, exercised across the real module
 * boundary rather than with hand-built fixtures).
 */
describe('Integration: event extraction -> persistence -> daily summary', () => {
  it('summarizes exactly the events the extractor produced, correctly traced', async () => {
    const extractor = new EventExtractor(fakeExtractionAdapter);
    const outcome = await extractor.extract(conversation);
    expect(outcome.rejected).toHaveLength(0);
    expect(outcome.valid).toHaveLength(2);

    const store = new InMemoryEventStore();
    for (const event of outcome.valid) {
      const validation = validateExtractedEvent(event);
      expect(validation.success).toBe(true);
      const record: EventRecord = {
        PK: Keys.elderPk(event.elderId),
        SK: Keys.eventSk(event.eventDate, event.eventId),
        GSI1PK: GSI1.pk(event.elderId, event.eventType),
        GSI1SK: GSI1.sk(event.eventDate),
        GSI2PK: GSI2.pk(event.elderId, event.reviewStatus),
        GSI2SK: GSI2.sk(event.eventDate, event.eventId),
        ...event,
        reviewHistory: [],
        updatedAt: event.createdAt,
        ttl: computeTtlEpochSeconds(RETENTION_DAYS.event),
      };
      await store.putItem(record);
    }
    expect(store.events).toHaveLength(2);

    const generator = new SummaryGenerator(store, fakeSummaryAdapter);
    const summary = await generator.generateDailySummary('elder-1', '2026-07-24');

    expect(summary.sourceEventIds.sort()).toEqual(['evt-activity-1', 'evt-meal-1']);
    expect(summary.content.meals).toEqual(['中午吃了地瓜稀飯']);
    expect(summary.content.activities).toEqual(['早上去公園散步半小時']);
    expect(store.savedSummary).toEqual(summary);
  });
});
