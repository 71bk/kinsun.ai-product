import { GuardrailEngine } from '../../guardrail/engine.js';
import type { GuardrailResult } from '../../guardrail/types.js';
import type { LlmGenerateResult } from '../../llm/types.js';

export interface GuardrailStageInput {
  elderId: string;
  traceId: string;
  llmResult: LlmGenerateResult;
}

/** Step Functions Task target for the `guardrail_check` node (H04). */
export async function handler(input: GuardrailStageInput): Promise<GuardrailResult> {
  const engine = new GuardrailEngine();
  return engine.check(input.llmResult.replyText, { elderId: input.elderId, conversationType: 'general_chat' });
}
