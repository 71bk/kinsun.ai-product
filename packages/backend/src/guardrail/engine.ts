import { ApplyGuardrailCommand, BedrockRuntimeClient, type ApplyGuardrailCommandOutput } from '@aws-sdk/client-bedrock-runtime';
import { detectEmergency } from './emergency.js';
import type { GuardrailContext, GuardrailResult } from './types.js';

const CONSULT_DOCTOR_MESSAGE = '這個問題建議您諮詢醫師';

function extractBlockedCategories(response: ApplyGuardrailCommandOutput): string[] {
  const categories: string[] = [];
  for (const assessment of response.assessments ?? []) {
    for (const topic of assessment.topicPolicy?.topics ?? []) {
      if (topic.action === 'BLOCKED') categories.push(topic.name ?? 'unknown_topic');
    }
    for (const filter of assessment.contentPolicy?.filters ?? []) {
      if (filter.action === 'BLOCKED') categories.push(filter.type ?? 'unknown_filter');
    }
  }
  return categories;
}

/**
 * GuardrailEngine (H04) — wraps Bedrock Guardrails' standalone
 * ApplyGuardrail API so arbitrary text (user input or model output) can be
 * safety-checked independent of any specific model call. Emergency
 * detection is checked first and short-circuits the Guardrails call
 * entirely: a life-safety instruction must never depend on an external
 * service being reachable.
 */
export class GuardrailEngine {
  constructor(
    private readonly client: BedrockRuntimeClient = new BedrockRuntimeClient({}),
    private readonly guardrailId: string = process.env.BEDROCK_GUARDRAIL_ID ?? '',
    private readonly guardrailVersion: string = process.env.BEDROCK_GUARDRAIL_VERSION ?? 'DRAFT',
  ) {}

  async check(content: string, context: GuardrailContext): Promise<GuardrailResult> {
    const emergency = detectEmergency(content);
    if (emergency) {
      return {
        allowed: true,
        action: 'pass',
        blockedCategories: [],
        safetyOverrideMessage: emergency.response,
      };
    }

    if (!this.guardrailId) {
      // No guardrail deployed to this environment yet — don't block
      // everything by default, but callers should log this as a gap.
      return { allowed: true, action: 'pass', blockedCategories: [] };
    }

    const response = await this.client.send(
      new ApplyGuardrailCommand({
        guardrailIdentifier: this.guardrailId,
        guardrailVersion: this.guardrailVersion,
        source: context.conversationType === 'health_query' ? 'OUTPUT' : 'INPUT',
        content: [{ text: { text: content } }],
      }),
    );

    const blockedCategories = extractBlockedCategories(response);
    const intervened = response.action === 'GUARDRAIL_INTERVENED';

    if (intervened && blockedCategories.length === 0) {
      // Guardrails intervened for a reason we couldn't parse into a named
      // category (e.g. a filter type future SDK versions add) — still block.
      blockedCategories.push('unspecified');
    }

    if (intervened) {
      return {
        allowed: false,
        action: 'block',
        blockedCategories,
        safetyOverrideMessage: CONSULT_DOCTOR_MESSAGE,
      };
    }

    const redacted = response.outputs?.[0]?.text;
    if (redacted && redacted !== content) {
      return { allowed: true, action: 'redact', blockedCategories, redactedContent: redacted };
    }

    return { allowed: true, action: 'pass', blockedCategories: [] };
  }
}
