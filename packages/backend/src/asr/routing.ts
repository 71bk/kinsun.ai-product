import type { AsrEndpoint, ConcreteLanguage } from './types.js';

/**
 * Property 1 (ASR 語言路由正確性): Mandarin/English always route to
 * Transcribe; Hokkien/Hakka always route to SageMaker. This function is the
 * single source of truth for that mapping — nothing else in the ASR module
 * should branch on language directly.
 */
export function routeEndpoint(language: ConcreteLanguage): AsrEndpoint {
  switch (language) {
    case 'zh-TW':
    case 'en-US':
      return 'transcribe';
    case 'nan-TW':
    case 'hak-TW':
      return 'sagemaker';
  }
}

export const SUPPORTED_LANGUAGES_BY_ENDPOINT: Record<AsrEndpoint, readonly ConcreteLanguage[]> = {
  transcribe: ['zh-TW', 'en-US'],
  sagemaker: ['nan-TW', 'hak-TW'],
};
