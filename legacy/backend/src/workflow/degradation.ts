import type { DegradedResponse } from '@elderly-care/shared';

/** Per-failure-scenario fallback content — see design.md §降級回應機制. */
export const DEGRADATION_STRATEGIES: Record<string, DegradedResponse> = {
  asr_timeout: {
    type: 'prerecorded_audio',
    content: '抱歉，我沒聽清楚，請再說一次好嗎？',
    audioUrl: 's3://assets/fallback/retry-please.mp3',
    retryAfterSeconds: 0,
  },
  llm_timeout: {
    type: 'prerecorded_audio',
    content: '系統正在忙碌，請等我一下再跟我說話喔',
    audioUrl: 's3://assets/fallback/system-busy.mp3',
    retryAfterSeconds: 5,
  },
  guardrail_blocked: {
    type: 'prerecorded_audio',
    content: '這個問題建議您諮詢醫師',
    audioUrl: 's3://assets/fallback/consult-doctor.mp3',
    retryAfterSeconds: 0,
  },
  tts_failure: {
    type: 'text_only',
    content: '（顯示文字回覆於畫面）',
    retryAfterSeconds: 0,
  },
  all_retries_exhausted: {
    type: 'prerecorded_audio',
    content: '不好意思，系統目前有點問題，請稍後再來找我聊天',
    audioUrl: 's3://assets/fallback/come-back-later.mp3',
    retryAfterSeconds: 60,
  },
};

export type DegradationScenario = keyof typeof DEGRADATION_STRATEGIES;

/**
 * Maps a failed nodeId + errorType to the degraded response the caller
 * should play/display. Falls back to `all_retries_exhausted` for anything
 * unrecognized rather than surfacing a raw error to the elder (A05.1).
 */
export function selectDegradedResponse(nodeId: string, errorType: string): DegradedResponse {
  if (nodeId === 'asr' && errorType === 'timeout') return DEGRADATION_STRATEGIES.asr_timeout!;
  if (nodeId === 'llm_generate' && errorType === 'timeout') return DEGRADATION_STRATEGIES.llm_timeout!;
  if (nodeId === 'guardrail_check') return DEGRADATION_STRATEGIES.guardrail_blocked!;
  if (nodeId === 'tts_synthesize') return DEGRADATION_STRATEGIES.tts_failure!;
  return DEGRADATION_STRATEGIES.all_retries_exhausted!;
}
