import type { EventRecord, ExtractedEvent } from '@elderly-care/shared';
import { computeTtlEpochSeconds, DynamoTable, GSI1, GSI2, Keys, RETENTION_DAYS } from '../db/index.js';
import { validateExtractedEvent } from './schema.js';

/**
 * Persists one extracted event as a DynamoDB item with its GSI1 (by
 * eventType) and GSI2 (by reviewStatus) projections auto-derived from the
 * event itself, so callers never hand-construct those keys and risk
 * drifting from the event's actual type/status (B01.2, B01.4, H03.1).
 *
 * Re-validates against the schema at the persistence boundary — even
 * though EventExtractor already validated, this is what makes Property 6
 * hold structurally rather than "by convention": nothing can reach
 * DynamoDB through this function without passing the gate.
 */
export async function persistEvent(table: DynamoTable, event: ExtractedEvent): Promise<EventRecord> {
  const validation = validateExtractedEvent(event);
  if (!validation.success) {
    throw new Error(`Refusing to persist an event that fails schema validation: ${validation.errors.join('; ')}`);
  }
  const e = validation.data;

  const record: EventRecord = {
    PK: Keys.elderPk(e.elderId),
    SK: Keys.eventSk(e.eventDate, e.eventId),
    GSI1PK: GSI1.pk(e.elderId, e.eventType),
    GSI1SK: GSI1.sk(e.eventDate),
    GSI2PK: GSI2.pk(e.elderId, e.reviewStatus),
    GSI2SK: GSI2.sk(e.eventDate, e.eventId),
    eventId: e.eventId,
    elderId: e.elderId,
    eventType: e.eventType,
    content: e.content,
    originalUtterance: e.originalUtterance,
    eventDate: e.eventDate,
    confidence: e.confidence,
    sourceConversationId: e.sourceConversationId,
    reviewStatus: e.reviewStatus,
    reviewHistory: [],
    createdAt: e.createdAt,
    updatedAt: e.createdAt,
    ttl: computeTtlEpochSeconds(RETENTION_DAYS.event),
  };

  await table.putItem(record);
  return record;
}
