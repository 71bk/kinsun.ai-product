import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { DynamoTable } from '../db/client.js';
import { validateExtractedEvent } from './schema.js';
import { persistEvent } from './persistence.js';
import { EventExtractor, type ExtractionAdapter } from './extractor.js';

const docClient = DynamoDBDocumentClient.from(new DynamoDBClient({}));
const ddbMock = mockClient(docClient);

const REQUIRED_STRING_FIELDS = [
  'eventId',
  'elderId',
  'content',
  'originalUtterance',
  'eventDate',
  'sourceConversationId',
  'createdAt',
] as const;

function validEventArb() {
  return fc.record({
    eventId: fc.uuid(),
    elderId: fc.constant('elder-1'),
    eventType: fc.constantFrom('meal', 'activity', 'sleep', 'medication_statement', 'emotion', 'important_event'),
    content: fc.string({ minLength: 1, maxLength: 100 }),
    originalUtterance: fc.string({ minLength: 1, maxLength: 100 }),
    eventDate: fc.constant('2026-07-24'),
    confidence: fc.float({ min: 0, max: 1, noNaN: true }),
    sourceConversationId: fc.uuid(),
    reviewStatus: fc.constantFrom('auto_approved', 'needs_review', 'caregiver_confirmed', 'caregiver_rejected'),
    createdAt: fc.constant('2026-07-24T00:00:00Z'),
    metadata: fc.constant({}),
  });
}

/**
 * Feature: elderly-care-ai-companion, Property 6: 結構化輸出 Schema 驗證閘門.
 * For any legal or illegal JSON structure produced by the Event Extractor,
 * output that fails schema validation must never be persisted.
 */
describe('Property 6: Structured-output schema validation gate', () => {
  it('every well-formed candidate validates and persists successfully', async () => {
    ddbMock.reset();
    ddbMock.onAnyCommand().resolves({});
    const table = new DynamoTable(undefined, docClient);

    await fc.assert(
      fc.asyncProperty(validEventArb(), async (candidate) => {
        const validation = validateExtractedEvent(candidate);
        expect(validation.success).toBe(true);
        await expect(persistEvent(table, candidate as never)).resolves.toBeDefined();
      }),
      { numRuns: 100 },
    );
  });

  it('a candidate missing any single required field never validates or persists', async () => {
    ddbMock.reset();
    ddbMock.onAnyCommand().resolves({});
    const table = new DynamoTable(undefined, docClient);

    await fc.assert(
      fc.asyncProperty(validEventArb(), fc.constantFrom(...REQUIRED_STRING_FIELDS), async (candidate, fieldToBreak) => {
        const broken = { ...candidate, [fieldToBreak]: '' };
        const validation = validateExtractedEvent(broken);
        expect(validation.success).toBe(false);
        await expect(persistEvent(table, broken as never)).rejects.toThrow();
      }),
      { numRuns: 100 },
    );
  });

  it('EventExtractor never places a schema-invalid candidate in the valid[] list', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(fc.oneof(validEventArb(), fc.object()), { minLength: 0, maxLength: 10 }),
        async (rawCandidates) => {
          const fakeAdapter: ExtractionAdapter = { async extractRaw() { return rawCandidates; } };
          const extractor = new EventExtractor(fakeAdapter);
          const outcome = await extractor.extract({
            PK: 'ELDER#e1',
            SK: 'CONV#1',
            conversationId: 'c1',
            elderId: 'e1',
            startTime: '2026-07-24T00:00:00Z',
            endTime: null,
            turns: [],
            asrMetadata: null,
            status: 'completed',
            traceId: 't1',
            audioS3Key: null,
            ttl: 0,
          });
          for (const validEvent of outcome.valid) {
            const revalidated = validateExtractedEvent({ ...validEvent, reviewStatus: validEvent.reviewStatus });
            expect(revalidated.success).toBe(true);
          }
          expect(outcome.valid.length + outcome.rejected.length).toBe(rawCandidates.length);
        },
      ),
      { numRuns: 100 },
    );
  });
});

/**
 * Feature: elderly-care-ai-companion, Property 7: 實體必要欄位完整性.
 * For any entity missing a different required field, persistence before
 * the entity contains all mandatory fields must be rejected.
 */
describe('Property 7: Entity required-field completeness', () => {
  it('rejects a candidate for each individually-missing required field', () => {
    fc.assert(
      fc.property(validEventArb(), fc.constantFrom(...REQUIRED_STRING_FIELDS), (candidate, fieldToRemove) => {
        const { [fieldToRemove]: _removed, ...withoutField } = candidate;
        const validation = validateExtractedEvent(withoutField);
        expect(validation.success).toBe(false);
      }),
      { numRuns: 100 },
    );
  });

  it('accepts a candidate once every required field is present', () => {
    fc.assert(
      fc.property(validEventArb(), (candidate) => {
        expect(validateExtractedEvent(candidate).success).toBe(true);
      }),
      { numRuns: 100 },
    );
  });
});
