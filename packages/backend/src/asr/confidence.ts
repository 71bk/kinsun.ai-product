/**
 * Property 2 (信心分數閾值分類): below threshold -> degrade (ask the elder to
 * repeat); at/above threshold -> proceed normally. Shared by the ASR layer
 * (A02.2) and the Event Extractor's needs_review gate (B01.5) — the
 * threshold value itself may differ per caller, but the boundary semantics
 * (>= passes) must not.
 */
export const ASR_CONFIDENCE_THRESHOLD = 0.6;

export function isConfidenceAcceptable(confidence: number, threshold: number = ASR_CONFIDENCE_THRESHOLD): boolean {
  return confidence >= threshold;
}

export const ASK_TO_REPEAT_MESSAGE = '不好意思，我沒聽清楚，可以請您再說一次嗎？';
