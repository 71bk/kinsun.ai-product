import { apiFetch, type ApiConfig } from './client';
import { assertNoRestrictedFields } from './family-guard';

export interface FamilyKnowledgeAnswer {
  status: 'ANSWER' | 'PARTIAL' | 'NO_DATA' | 'CLARIFY' | 'BLOCKED' | 'UNAVAILABLE';
  answer: string;
  sources: { title: string; url: string; locator: string; current_status: 'current' | 'unknown' }[];
}

function invalid(): never {
  throw new Error('Invalid public knowledge response');
}

export async function askFamilyKnowledge(
  config: ApiConfig,
  question: string,
  language: 'zh-TW' | 'en-US',
  signal?: AbortSignal,
): Promise<FamilyKnowledgeAnswer> {
  const raw = await apiFetch<unknown>(config, '/api/v1/family/knowledge/questions', {
    method: 'POST',
    body: JSON.stringify({ question, language }),
    signal,
  });
  assertNoRestrictedFields(raw);
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return invalid();
  const data = raw as Record<string, unknown>;
  if (
    Object.keys(data).some((key) => !['status', 'answer', 'sources'].includes(key)) ||
    !['ANSWER', 'PARTIAL', 'NO_DATA', 'CLARIFY', 'BLOCKED', 'UNAVAILABLE'].includes(
      String(data.status),
    ) ||
    typeof data.answer !== 'string' ||
    !data.answer.trim() ||
    data.answer.length > 50000 ||
    !Array.isArray(data.sources) ||
    data.sources.length > 5
  )
    return invalid();
  const supported = data.status === 'ANSWER' || data.status === 'PARTIAL';
  if (supported !== data.sources.length > 0) return invalid();
  for (const source of data.sources) {
    if (
      !source ||
      typeof source !== 'object' ||
      Array.isArray(source) ||
      Object.keys(source).some(
        (key) => !['title', 'url', 'locator', 'current_status'].includes(key),
      ) ||
      typeof source.title !== 'string' ||
      !source.title.trim() ||
      source.title.length > 512 ||
      typeof source.locator !== 'string' ||
      !source.locator.trim() ||
      source.locator.length > 2048 ||
      typeof source.url !== 'string' ||
      source.url.length > 4096 ||
      !['current', 'unknown'].includes(source.current_status)
    )
      return invalid();
    let url: URL;
    try {
      url = new URL(source.url);
    } catch {
      return invalid();
    }
    if (
      !['https:', 'http:'].includes(url.protocol) ||
      !url.hostname.endsWith('.gov.tw') ||
      url.username ||
      url.password ||
      /[\s\\]/.test(source.url)
    )
      return invalid();
  }
  return raw as FamilyKnowledgeAnswer;
}
