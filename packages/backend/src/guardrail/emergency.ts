export type EmergencySeverity = 'critical' | 'high' | 'medium';

export interface EmergencyPattern {
  id: string;
  keywords: readonly string[];
  response: string;
  notifyFamily: boolean;
  severity: EmergencySeverity;
}

/**
 * Fixed safety instructions for life-threatening situations (H04.2). These
 * bypass the LLM entirely — the response is a constant string, never
 * model-generated, so it can't be softened, hedged, or omitted.
 */
export const EMERGENCY_PATTERNS: readonly EmergencyPattern[] = [
  {
    id: 'chest_pain',
    keywords: ['胸痛', '胸口痛', '胸口很痛', '心臟痛', '胸悶', '胸口不舒服', '喘不過氣', '呼吸困難'],
    response: '胸口不舒服要趕快打 119 叫救護車，也請家人過來陪您',
    notifyFamily: true,
    severity: 'critical',
  },
  {
    id: 'fall',
    keywords: ['跌倒', '摔倒', '滑倒了'],
    response: '跌倒的話先不要亂動，請家人或鄰居來幫忙，需要的話打 119',
    notifyFamily: true,
    severity: 'critical',
  },
  {
    id: 'unconscious',
    keywords: ['意識不清', '昏倒', '昏迷', '不省人事', '叫不醒'],
    response: '如果有人意識不清，請立即撥打 119',
    notifyFamily: true,
    severity: 'critical',
  },
];

/** Returns the first matching emergency pattern for `text`, or null if none match. */
export function detectEmergency(text: string): EmergencyPattern | null {
  return EMERGENCY_PATTERNS.find((pattern) => pattern.keywords.some((kw) => text.includes(kw))) ?? null;
}
