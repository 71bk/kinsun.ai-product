import { type ApiConfig } from './client';
import { askPublicKnowledge } from './public-knowledge';
export type { PublicKnowledgeAnswer as StaffKnowledgeAnswer } from './public-knowledge';

export function askStaffKnowledge(
  config: ApiConfig,
  question: string,
  language: 'zh-TW' | 'en-US',
  signal?: AbortSignal,
) {
  return askPublicKnowledge('staff', config, question, language, signal);
}
