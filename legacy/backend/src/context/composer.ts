import type { ConfirmedMemory, MemoryRecord } from '@elderly-care/shared';
import { allocateBudget } from './budget.js';
import { buildContextItems, buildHistoryItems, packWithinBudget } from './items.js';
import { buildSystemPrompt } from './prompt.js';
import type { ContextComposeInputs, ContextRequest, ContextResult } from './types.js';

function toConfirmedMemory(m: MemoryRecord): ConfirmedMemory {
  return {
    memoryId: m.memoryId,
    elderId: m.elderId,
    category: m.category,
    content: m.content,
    confirmedBy: m.confirmedBy ?? '',
    confirmedAt: m.confirmedAt ?? '',
    sourceConversationId: m.sourceConversationId,
    isActive: m.isActive,
    lastUsedAt: m.lastUsedAt,
  };
}

/**
 * ContextComposer (J02) — assembles the bounded prompt for one LLM turn.
 * Two invariants hold regardless of input size (Properties 4 & 5):
 *  1. totalTokens never exceeds request.tokenBudget.
 *  2. confirmedMemories in the result only ever contains status==='confirmed'
 *     && isActive memories — pending/rejected/deleted ones are filtered out
 *     in items.ts before packing even sees them.
 */
export class ContextComposer {
  compose(request: ContextRequest, inputs: ContextComposeInputs): ContextResult {
    const systemPrompt = buildSystemPrompt(inputs.persona);
    const allocation = allocateBudget(request.tokenBudget);

    const staticItems = buildContextItems(systemPrompt, inputs);
    const historyItems = buildHistoryItems(request.conversationHistory);

    const { included, totalTokens } = packWithinBudget(
      [...staticItems, ...historyItems],
      allocation,
      request.tokenBudget,
    );

    const includedIds = new Set(included.map((i) => i.id));

    const confirmedMemories = inputs.memories
      .filter((m) => m.status === 'confirmed' && m.isActive && includedIds.has(m.memoryId))
      .map(toConfirmedMemory);

    const searchResults = inputs.searchResults.filter((r) => includedIds.has(r.chunkId));

    return {
      systemPrompt,
      persona: inputs.persona,
      recentSummary: includedIds.has('summary') ? inputs.recentSummary : null,
      confirmedMemories,
      situationalContext: inputs.situationalContext,
      searchResults: searchResults.length > 0 ? searchResults : null,
      usedItems: included,
      totalTokens,
    };
  }
}
