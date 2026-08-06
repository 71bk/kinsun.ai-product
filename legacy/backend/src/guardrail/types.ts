export type ConversationType = 'general_chat' | 'health_query' | 'memory_confirmation';

export interface GuardrailContext {
  elderId: string;
  conversationType: ConversationType;
}

export type GuardrailActionResult = 'pass' | 'block' | 'redact';

export interface GuardrailResult {
  allowed: boolean;
  action: GuardrailActionResult;
  blockedCategories: string[];
  redactedContent?: string;
  safetyOverrideMessage?: string;
}

/** Topics Bedrock Guardrails is configured to intercept (H04.1). */
export const MEDICAL_GUARDRAIL_TOPICS = [
  'diagnosis',
  'medication_change',
  'treatment_decision',
  'dosage_recommendation',
] as const;

export interface GuardrailTestCase {
  id: string;
  input: string;
  expectedAction: 'pass' | 'block';
  category: string;
  description: string;
}
