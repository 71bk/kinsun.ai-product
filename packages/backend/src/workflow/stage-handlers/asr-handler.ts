import type { PersonaRecord } from '@elderly-care/shared';
import { ASREngine } from '../../asr/engine.js';
import { TranscribeAdapter, SageMakerAdapter } from '../../asr/adapters.js';
import type { AudioInput } from '../../asr/types.js';
import { DynamoTable, Keys } from '../../db/index.js';

export interface AsrStageInput {
  elderId: string;
  traceId: string;
  audio: { audioBase64: string; encoding: 'pcm' | 'opus'; sampleRate: number };
}

export interface AsrStageOutput {
  degraded: boolean;
  message?: string;
  text: string;
  language: string;
  confidence: number;
  serviceEndpoint: string;
  modelVersion: string;
  latencyMs: number;
}

/** Step Functions Task target for the `asr` node (design.md's ASR stage). */
export async function handler(input: AsrStageInput): Promise<AsrStageOutput> {
  const table = new DynamoTable();
  const persona = await table.getItem<PersonaRecord>(Keys.elderPk(input.elderId), Keys.personaSk());
  const preferredLanguage = persona?.preferredLanguage ?? 'zh-TW';

  const engine = new ASREngine({
    transcribeAdapter: new TranscribeAdapter(),
    sageMakerAdapter: new SageMakerAdapter(),
    traceId: input.traceId,
  });

  const audio: AudioInput = {
    data: Buffer.from(input.audio.audioBase64, 'base64'),
    encoding: input.audio.encoding,
    sampleRate: input.audio.sampleRate,
  };

  const outcome = await engine.transcribe(audio, {
    elderId: input.elderId,
    preferredLanguage,
    sampleRate: input.audio.sampleRate,
    encoding: input.audio.encoding,
  });

  if (outcome.degraded || !outcome.result) {
    return {
      degraded: true,
      message: outcome.message,
      text: '',
      language: preferredLanguage,
      confidence: 0,
      serviceEndpoint: 'none',
      modelVersion: 'none',
      latencyMs: 0,
    };
  }

  return {
    degraded: false,
    text: outcome.result.text,
    language: outcome.result.language,
    confidence: outcome.result.confidence,
    serviceEndpoint: outcome.result.serviceEndpoint,
    modelVersion: outcome.result.modelVersion,
    latencyMs: outcome.result.latencyMs,
  };
}
