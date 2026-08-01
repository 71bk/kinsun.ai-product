import type { LlmGenerateRequest } from './types.js';

/**
 * Renders the grounding data (confirmed memories, summary, situational
 * context, search results) into the user turn actually sent to the model.
 * This is a second line of defense for A04.2 alongside the system prompt:
 * even though the caller only ever hands us confirmed+active memories
 * (Property 5 is enforced upstream in Context Composer), the wording here
 * still frames them as "reference, defer to what the elder just said" so a
 * stale memory doesn't get asserted back at the elder as certain fact.
 */
export function buildUserMessage(request: LlmGenerateRequest): string {
  const parts: string[] = [];

  if (request.confirmedMemories.length > 0) {
    parts.push('已知資訊（僅供參考，如與長者現在所說的不同，請以長者現在說的為準並可禮貌詢問）：');
    parts.push(...request.confirmedMemories.map((m) => `- ${m.content}`));
  }

  if (request.recentSummary) {
    parts.push(`最近生活摘要：${request.recentSummary}`);
  }

  parts.push(`目前時間：${request.situationalContext.currentTime}（${request.situationalContext.dayOfWeek}）`);
  if (request.situationalContext.weather) {
    parts.push(`天氣：${request.situationalContext.weather.condition}，${request.situationalContext.weather.temperatureC}°C`);
  }

  if (request.searchResults && request.searchResults.length > 0) {
    parts.push('相關衛教資訊（回答時請標明來源，且僅供參考不作為醫療診斷依據）：');
    parts.push(...request.searchResults.map((r) => `- [${r.documentTitle}／${r.sourceAgency}] ${r.content}`));
  }

  parts.push(`長者說：「${request.currentUtterance}」`);
  return parts.join('\n');
}
