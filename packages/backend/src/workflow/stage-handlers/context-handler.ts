import { ContextComposer } from '../../context/composer.js';
import { loadContextInputs } from '../../context/data-provider.js';
import type { ContextResult } from '../../context/types.js';
import type { AsrStageOutput } from './asr-handler.js';

export interface ContextStageInput {
  elderId: string;
  traceId: string;
  asrResult: AsrStageOutput;
}

/** Step Functions Task target for the `context_compose` node. */
export async function handler(input: ContextStageInput): Promise<ContextResult> {
  const inputs = await loadContextInputs(input.elderId);
  const composer = new ContextComposer();
  return composer.compose(
    {
      elderId: input.elderId,
      currentUtterance: input.asrResult.text,
      conversationHistory: [],
      tokenBudget: 4096,
    },
    inputs,
  );
}
