import type { Language } from '@elderly-care/shared';

export interface ASRConfig {
  elderId: string;
  preferredLanguage: Language;
  sampleRate: number; // 16000Hz
  encoding: 'pcm' | 'opus';
}

export interface AudioInput {
  data: Uint8Array;
  encoding: 'pcm' | 'opus';
  sampleRate: number;
}

export interface TranscriptSegment {
  text: string;
  startTime: number;
  endTime: number;
  confidence: number;
  language: Language;
}

export interface TranscriptionResult {
  text: string;
  language: Language;
  confidence: number;
  serviceEndpoint: string;
  modelVersion: string;
  latencyMs: number;
  segments: TranscriptSegment[];
}

export type ConcreteLanguage = Exclude<Language, 'mixed'>;

export type AsrEndpoint = 'transcribe' | 'sagemaker';
