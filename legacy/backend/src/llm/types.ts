import type { ConfirmedMemory, PersonaContext, SearchResult } from '@elderly-care/shared';
import type { SituationalContext } from '../context/types.js';

export interface LlmGenerateRequest {
  systemPrompt: string;
  persona: PersonaContext;
  currentUtterance: string;
  confirmedMemories: ConfirmedMemory[];
  recentSummary: string | null;
  situationalContext: SituationalContext;
  searchResults: SearchResult[] | null;
  conversationHistory: { role: 'elder' | 'assistant'; content: string }[];
}

export interface LlmGenerateResult {
  replyText: string;
  modelId: string;
  stopReason: string | null;
  inputTokens: number;
  outputTokens: number;
}
