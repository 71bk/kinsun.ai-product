import type { ConcreteLanguage, TtsEndpoint } from './types.js';

/** Mandarin/English -> Polly; Hokkien/Hakka -> the self-hosted SageMaker TTS endpoint (A03.2, A03.3). */
export function routeTtsEndpoint(language: ConcreteLanguage): TtsEndpoint {
  switch (language) {
    case 'zh-TW':
    case 'en-US':
      return 'polly';
    case 'nan-TW':
    case 'hak-TW':
      return 'sagemaker';
  }
}
