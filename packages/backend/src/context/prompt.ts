import type { PersonaContext } from '@elderly-care/shared';

/**
 * Base system prompt. The "don't fabricate" instruction (A04.3) and the
 * "confirmed memories are the only facts" instruction (A04.2) are stated
 * explicitly here as a defense-in-depth measure — the *structural*
 * guarantee that candidate memories never appear in the prompt comes from
 * items.ts's Property-5 filter, but telling the model the rule too means a
 * stray fact-shaped sentence elsewhere in the prompt doesn't get treated as
 * ground truth either.
 */
export function buildSystemPrompt(persona: PersonaContext): string {
  const lengthGuide: Record<PersonaContext['responseLength'], string> = {
    short: '簡短（一兩句話）',
    medium: '中等長度',
    long: '較詳細',
  };
  const styleGuide: Record<PersonaContext['interactionStyle'], string> = {
    formal: '正式有禮',
    casual: '輕鬆自然',
    warm: '溫暖親切',
  };

  return [
    '你是一位陪伴長者的語音助理。你的角色是傾聽、陪伴與協助記錄生活，不是醫療專業人員。',
    `請以「${persona.displayName}」稱呼使用者，語氣${styleGuide[persona.interactionStyle]}，回覆長度${lengthGuide[persona.responseLength]}。`,
    '只能將標記為「已確認記憶」的內容當作已知事實使用；未確認的候選記憶絕不可作為事實引用。',
    '如果沒有足夠資訊回答問題，請誠實告知不知道，絕不可虛構資訊。',
    '不得提供診斷、停藥、改藥或治療決策等醫療建議；相關問題請建議使用者諮詢醫師。',
  ].join('\n');
}
