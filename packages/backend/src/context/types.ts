import type { ConfirmedMemory, ConversationTurn, MemoryRecord, PersonaContext, SearchResult } from '@elderly-care/shared';

export type ContextItemType =
  | 'system_prompt'
  | 'persona'
  | 'memory'
  | 'summary'
  | 'search_result'
  | 'situational'
  | 'history_turn';

/** One addressable unit of prompt content — the atom Property 4/usedItems tracking operates on. */
export interface ContextItem {
  id: string;
  type: ContextItemType;
  content: string;
  tokens: number;
}

export interface WeatherInfo {
  condition: string;
  temperatureC: number;
}

export interface SituationalContext {
  currentTime: string; // ISO 8601
  dayOfWeek: string;
  weather: WeatherInfo | null;
  recentInteractionCount: number;
  lastInteractionTime: string | null;
}

/** Per-category token budgets — must always sum to <= the requested total (Property 4). */
export interface TokenBudgetAllocation {
  systemPrompt: number;
  persona: number;
  memories: number;
  recentSummary: number;
  searchResults: number;
  conversationHistory: number;
}

export interface ContextRequest {
  elderId: string;
  currentUtterance: string;
  conversationHistory: ConversationTurn[];
  tokenBudget: number; // e.g., 4096
}

/**
 * Raw inputs the composer packs into a prompt. `memories` intentionally
 * includes both confirmed and candidate/pending/rejected records — the
 * composer itself is responsible for filtering to confirmed-only (Property
 * 5), which is what makes that filtering independently testable.
 */
export interface ContextComposeInputs {
  persona: PersonaContext;
  recentSummary: string | null;
  memories: MemoryRecord[];
  situationalContext: SituationalContext;
  searchResults: SearchResult[];
}

export interface ContextResult {
  systemPrompt: string;
  persona: PersonaContext;
  recentSummary: string | null;
  confirmedMemories: ConfirmedMemory[];
  situationalContext: SituationalContext;
  searchResults: SearchResult[] | null;
  usedItems: ContextItem[];
  totalTokens: number;
}
