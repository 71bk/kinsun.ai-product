import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { ConversationTurn, MemoryRecord, MemoryStatus, PersonaContext, SearchResult } from '@elderly-care/shared';
import { ContextComposer } from './composer.js';
import type { ContextComposeInputs, ContextRequest } from './types.js';

const personaArb: fc.Arbitrary<PersonaContext> = fc.record({
  displayName: fc.constantFrom('林阿嬤', '陳阿公', '王奶奶'),
  preferredLanguage: fc.constantFrom('zh-TW', 'nan-TW', 'hak-TW', 'en-US', 'mixed'),
  responseLength: fc.constantFrom('short', 'medium', 'long'),
  speakingSpeed: fc.constantFrom('slow', 'normal', 'fast'),
  interactionStyle: fc.constantFrom('formal', 'casual', 'warm'),
  customGreeting: fc.string({ maxLength: 20 }),
});

const memoryStatusArb = fc.constantFrom<MemoryStatus>('pending', 'confirmed', 'rejected', 'deleted');

function memoryArb(): fc.Arbitrary<MemoryRecord> {
  return fc.record({
    PK: fc.constant('ELDER#elder-1'),
    SK: fc.string(),
    memoryId: fc.uuid(),
    elderId: fc.constant('elder-1'),
    category: fc.constantFrom('preference', 'relationship', 'routine', 'health_condition', 'life_event'),
    content: fc.string({ minLength: 1, maxLength: 200 }),
    sourceConversationId: fc.constant('conv-1'),
    confidence: fc.float({ min: 0, max: 1, noNaN: true }),
    status: memoryStatusArb,
    confirmedBy: fc.option(fc.string(), { nil: null }),
    confirmedAt: fc.option(fc.string(), { nil: null }),
    isActive: fc.boolean(),
    lastUsedAt: fc.constant(null),
    createdAt: fc.constant('2026-01-01T00:00:00Z'),
    updatedAt: fc.constant('2026-01-01T00:00:00Z'),
    auditTrail: fc.constant([]),
    ttl: fc.constant(null),
  }) as fc.Arbitrary<MemoryRecord>;
}

const searchResultArb: fc.Arbitrary<SearchResult> = fc.record({
  chunkId: fc.uuid(),
  documentId: fc.uuid(),
  content: fc.string({ minLength: 1, maxLength: 300 }),
  sourceAgency: fc.constant('衛生福利部'),
  documentTitle: fc.constant('長者衛教手冊'),
  publishDate: fc.constant('2026-01-01'),
  bm25Score: fc.float({ min: 0, max: 10, noNaN: true }),
  vectorScore: fc.float({ min: 0, max: 1, noNaN: true }),
  combinedScore: fc.float({ min: 0, max: 10, noNaN: true }),
  metadata: fc.constant({
    sourceAgency: '衛生福利部',
    serviceType: 'health',
    region: 'TW',
    effectiveDate: '2026-01-01',
    expiryDate: null,
    riskLevel: 'low',
    reviewStatus: 'approved',
    version: '1',
  }),
});

const historyTurnArb: fc.Arbitrary<ConversationTurn> = fc.record({
  role: fc.constantFrom('elder', 'assistant'),
  content: fc.string({ minLength: 1, maxLength: 100 }),
  timestamp: fc.constant('2026-01-01T00:00:00Z'),
  language: fc.constant('zh-TW'),
});

const inputsArb: fc.Arbitrary<ContextComposeInputs> = fc.record({
  persona: personaArb,
  recentSummary: fc.option(fc.string({ minLength: 1, maxLength: 300 }), { nil: null }),
  memories: fc.array(memoryArb(), { maxLength: 15 }),
  situationalContext: fc.constant({
    currentTime: '2026-07-24T09:00:00Z',
    dayOfWeek: 'Friday',
    weather: null,
    recentInteractionCount: 3,
    lastInteractionTime: null,
  }),
  searchResults: fc.array(searchResultArb, { maxLength: 10 }),
});

/**
 * Feature: elderly-care-ai-companion, Property 4: Context Composer Token 預算約束.
 * For any set of available context items and any token budget, the
 * produced prompt's token count never exceeds the budget, and usedItems
 * exactly reflects what was actually included.
 */
describe('Property 4: Context Composer token budget constraint', () => {
  it('never exceeds the requested token budget, across arbitrary inputs and budgets', () => {
    fc.assert(
      fc.property(
        inputsArb,
        fc.array(historyTurnArb, { maxLength: 20 }),
        fc.integer({ min: 0, max: 8000 }),
        (inputs, history, tokenBudget) => {
          const composer = new ContextComposer();
          const request: ContextRequest = {
            elderId: 'elder-1',
            currentUtterance: '你好',
            conversationHistory: history,
            tokenBudget,
          };
          const result = composer.compose(request, inputs);
          expect(result.totalTokens).toBeLessThanOrEqual(tokenBudget);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('totalTokens always equals the sum of usedItems tokens (usedItems traceability)', () => {
    fc.assert(
      fc.property(inputsArb, fc.array(historyTurnArb, { maxLength: 10 }), fc.integer({ min: 0, max: 4096 }), (inputs, history, tokenBudget) => {
        const composer = new ContextComposer();
        const result = composer.compose(
          { elderId: 'elder-1', currentUtterance: 'hi', conversationHistory: history, tokenBudget },
          inputs,
        );
        const sum = result.usedItems.reduce((acc, item) => acc + item.tokens, 0);
        expect(result.totalTokens).toBe(sum);
      }),
      { numRuns: 200 },
    );
  });
});

/**
 * Feature: elderly-care-ai-companion, Property 5: 僅已確認記憶作為事實.
 * For any mixed set of confirmed and candidate/rejected/deleted memories,
 * the composer's output only ever contains status==='confirmed' &&
 * isActive memories in its fact section.
 */
describe('Property 5: Only confirmed memories are used as facts', () => {
  it('confirmedMemories in the result never includes a non-confirmed or inactive memory', () => {
    fc.assert(
      fc.property(inputsArb, fc.integer({ min: 0, max: 4096 }), (inputs, tokenBudget) => {
        const composer = new ContextComposer();
        const result = composer.compose(
          { elderId: 'elder-1', currentUtterance: 'hi', conversationHistory: [], tokenBudget },
          inputs,
        );
        for (const mem of result.confirmedMemories) {
          const source = inputs.memories.find((m) => m.memoryId === mem.memoryId);
          expect(source).toBeDefined();
          expect(source!.status).toBe('confirmed');
          expect(source!.isActive).toBe(true);
        }
      }),
      { numRuns: 200 },
    );
  });

  it('with a large budget, every confirmed+active memory is included and no non-confirmed one is', () => {
    fc.assert(
      fc.property(inputsArb, (inputs) => {
        const composer = new ContextComposer();
        // Budget generous enough that packing limits shouldn't bind.
        const result = composer.compose(
          { elderId: 'elder-1', currentUtterance: 'hi', conversationHistory: [], tokenBudget: 1_000_000 },
          inputs,
        );
        const expectedConfirmedIds = new Set(
          inputs.memories.filter((m) => m.status === 'confirmed' && m.isActive).map((m) => m.memoryId),
        );
        const actualIds = new Set(result.confirmedMemories.map((m) => m.memoryId));
        expect(actualIds).toEqual(expectedConfirmedIds);
      }),
      { numRuns: 100 },
    );
  });
});
