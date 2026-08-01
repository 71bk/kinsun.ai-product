import { estimateTokens } from './tokens.js';
import type { ContextComposeInputs, ContextItem, TokenBudgetAllocation } from './types.js';

const CATEGORY_BY_TYPE: Record<ContextItem['type'], keyof TokenBudgetAllocation> = {
  system_prompt: 'systemPrompt',
  persona: 'persona',
  memory: 'memories',
  summary: 'recentSummary',
  search_result: 'searchResults',
  situational: 'systemPrompt', // situational context rides along with the system prompt budget
  history_turn: 'conversationHistory',
};

/**
 * Converts raw inputs into addressable ContextItems. This is the single
 * point where Property 5 (只確認記憶作為事實) is enforced: memories whose
 * status isn't 'confirmed', or that are inactive, never become an item —
 * so they cannot appear in usedItems or the assembled prompt no matter what
 * the budget packer does downstream.
 */
export function buildContextItems(systemPrompt: string, inputs: ContextComposeInputs): ContextItem[] {
  const items: ContextItem[] = [
    { id: 'system_prompt', type: 'system_prompt', content: systemPrompt, tokens: estimateTokens(systemPrompt) },
    {
      id: 'situational',
      type: 'situational',
      content: JSON.stringify(inputs.situationalContext),
      tokens: estimateTokens(JSON.stringify(inputs.situationalContext)),
    },
  ];

  if (inputs.recentSummary) {
    items.push({
      id: 'summary',
      type: 'summary',
      content: inputs.recentSummary,
      tokens: estimateTokens(inputs.recentSummary),
    });
  }

  for (const memory of inputs.memories) {
    if (memory.status !== 'confirmed' || !memory.isActive) continue; // Property 5 gate
    items.push({
      id: memory.memoryId,
      type: 'memory',
      content: memory.content,
      tokens: estimateTokens(memory.content),
    });
  }

  for (const result of inputs.searchResults) {
    items.push({
      id: result.chunkId,
      type: 'search_result',
      content: result.content,
      tokens: estimateTokens(result.content),
    });
  }

  return items;
}

export function buildHistoryItems(history: { content: string }[]): ContextItem[] {
  // Most recent turns are the most valuable when the budget is tight —
  // pack from the end of the conversation backwards.
  return [...history].reverse().map((turn, i) => ({
    id: `history_${i}`,
    type: 'history_turn' as const,
    content: turn.content,
    tokens: estimateTokens(turn.content),
  }));
}

export interface PackResult {
  included: ContextItem[];
  totalTokens: number;
}

/**
 * Packs items into their per-category budgets. system_prompt/persona/
 * situational are mandatory (always attempted first within their own
 * budget); everything else is included greedily while it still fits both
 * its category budget and — as a final invariant — the overall total.
 * Property 4 requires the produced total never exceeds the requested
 * budget; capping every category independently, then re-checking the
 * running grand total on every insertion, guarantees that even if
 * category budgets round oddly the sum still can't exceed totalBudget.
 */
export function packWithinBudget(items: ContextItem[], allocation: TokenBudgetAllocation, totalBudget: number): PackResult {
  const spentByCategory: Record<keyof TokenBudgetAllocation, number> = {
    systemPrompt: 0,
    persona: 0,
    memories: 0,
    recentSummary: 0,
    searchResults: 0,
    conversationHistory: 0,
  };
  const included: ContextItem[] = [];
  let totalTokens = 0;

  for (const item of items) {
    const category = CATEGORY_BY_TYPE[item.type];
    const categoryBudget = allocation[category];
    const wouldSpendInCategory = spentByCategory[category] + item.tokens;
    const wouldSpendOverall = totalTokens + item.tokens;

    if (wouldSpendInCategory > categoryBudget) continue;
    if (wouldSpendOverall > totalBudget) continue;

    included.push(item);
    spentByCategory[category] = wouldSpendInCategory;
    totalTokens = wouldSpendOverall;
  }

  return { included, totalTokens };
}
