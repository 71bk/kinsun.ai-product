import { LlmEngine } from '../../llm/engine.js';
import type { LlmGenerateResult } from '../../llm/types.js';
import type { ContextResult } from '../../context/types.js';
import type { AsrStageOutput } from './asr-handler.js';

export interface LlmStageInput {
  elderId: string;
  traceId: string;
  asrResult: AsrStageOutput;
  contextResult: ContextResult;
}

/** Step Functions Task target for the `llm_generate` node. */
export async function handler(input: LlmStageInput): Promise<LlmGenerateResult> {
  const engine = new LlmEngine();
  return engine.generate({
    systemPrompt: input.contextResult.systemPrompt,
    persona: input.contextResult.persona,
    currentUtterance: input.asrResult.text,
    confirmedMemories: input.contextResult.confirmedMemories,
    recentSummary: input.contextResult.recentSummary,
    situationalContext: input.contextResult.situationalContext,
    searchResults: input.contextResult.searchResults,
    conversationHistory: [],
  });
}
