import type { WorkflowNodeConfig } from '@elderly-care/shared';

/**
 * Voice interaction workflow node configs — see design.md §協調層.
 * lambdaArn/inputSchema/outputSchema are filled in by the CDK stack at
 * deploy time (real ARNs aren't known until the corresponding Lambda
 * exists); this module owns the timeout/retry/fallback policy per node,
 * which is what Property 3 (bounded retries) and the ASL definition both
 * need to agree on.
 */
export const VOICE_INTERACTION_NODES: readonly WorkflowNodeConfig[] = [
  {
    nodeId: 'asr',
    lambdaArn: '',
    inputSchema: {},
    outputSchema: {},
    timeoutSeconds: 10,
    retryPolicy: { maxAttempts: 2, intervalSeconds: 1, backoffRate: 2, retryableErrors: ['ServiceUnavailable'] },
    fallbackAction: { type: 'default_response', message: '抱歉，我沒聽清楚，請再說一次' },
  },
  {
    nodeId: 'context_compose',
    lambdaArn: '',
    inputSchema: {},
    outputSchema: {},
    timeoutSeconds: 5,
    retryPolicy: { maxAttempts: 1, intervalSeconds: 0, backoffRate: 1, retryableErrors: [] },
    fallbackAction: { type: 'skip_node' },
  },
  {
    nodeId: 'llm_generate',
    lambdaArn: '',
    inputSchema: {},
    outputSchema: {},
    timeoutSeconds: 15,
    retryPolicy: { maxAttempts: 2, intervalSeconds: 2, backoffRate: 2, retryableErrors: ['ThrottlingException'] },
    fallbackAction: { type: 'default_response', message: '系統忙碌中，請稍後再試' },
  },
  {
    nodeId: 'guardrail_check',
    lambdaArn: '',
    inputSchema: {},
    outputSchema: {},
    timeoutSeconds: 3,
    retryPolicy: { maxAttempts: 1, intervalSeconds: 0, backoffRate: 1, retryableErrors: [] },
    fallbackAction: { type: 'default_response', message: '這個問題建議您諮詢醫師' },
  },
  {
    nodeId: 'tts_synthesize',
    lambdaArn: '',
    inputSchema: {},
    outputSchema: {},
    timeoutSeconds: 10,
    retryPolicy: { maxAttempts: 2, intervalSeconds: 1, backoffRate: 2, retryableErrors: ['ServiceUnavailable'] },
    fallbackAction: { type: 'skip_node' }, // 降級為文字顯示
  },
] as const;

/** Global cap on total retries across an entire interaction, independent of any one node's maxAttempts. */
export const GLOBAL_MAX_RETRIES = 6;

export function getNodeConfig(nodeId: string): WorkflowNodeConfig | undefined {
  return VOICE_INTERACTION_NODES.find((n) => n.nodeId === nodeId);
}
