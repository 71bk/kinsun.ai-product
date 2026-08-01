import type { Language } from '@elderly-care/shared';

export type ConcreteLanguage = Exclude<Language, 'mixed'>;
export type TtsEndpoint = 'polly' | 'sagemaker';

export interface TtsConfig {
  language: ConcreteLanguage;
  speakingSpeed: 'slow' | 'normal' | 'fast';
}

export interface TtsAudioResult {
  audio: Uint8Array;
  contentType: string;
  serviceEndpoint: TtsEndpoint;
  latencyMs: number;
}

/** synthesize() never throws for a downstream TTS failure — it degrades to text (A03.4). */
export interface TtsOutcome {
  degraded: boolean;
  audio?: TtsAudioResult;
  textFallback?: string;
}
