import type { TokenBudgetAllocation } from './types.js';

/**
 * Reference allocation at the design's default 4096-token budget (design.md
 * §Token 預算分配策略). Other budgets scale each category proportionally so
 * the *shape* of the allocation is preserved regardless of total size.
 */
const REFERENCE_TOTAL = 4096;
const REFERENCE_ALLOCATION: Omit<TokenBudgetAllocation, 'conversationHistory'> = {
  systemPrompt: 500,
  persona: 200,
  memories: 500,
  recentSummary: 300,
  searchResults: 1000,
};

/**
 * Splits `totalBudget` across categories. Every fixed category is scaled by
 * totalBudget/REFERENCE_TOTAL and floored, so their sum is always strictly
 * <= totalBudget; conversationHistory receives whatever remains (never
 * negative). This is what guarantees Property 4 by construction rather
 * than by runtime clamping.
 */
export function allocateBudget(totalBudget: number): TokenBudgetAllocation {
  const safeBudget = Math.max(0, totalBudget);
  const scale = safeBudget / REFERENCE_TOTAL;

  const systemPrompt = Math.floor(REFERENCE_ALLOCATION.systemPrompt * scale);
  const persona = Math.floor(REFERENCE_ALLOCATION.persona * scale);
  const memories = Math.floor(REFERENCE_ALLOCATION.memories * scale);
  const recentSummary = Math.floor(REFERENCE_ALLOCATION.recentSummary * scale);
  const searchResults = Math.floor(REFERENCE_ALLOCATION.searchResults * scale);

  const fixedSum = systemPrompt + persona + memories + recentSummary + searchResults;
  const conversationHistory = Math.max(0, safeBudget - fixedSum);

  return { systemPrompt, persona, memories, recentSummary, searchResults, conversationHistory };
}
