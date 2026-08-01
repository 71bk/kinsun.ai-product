import { GetObjectCommand, PutObjectCommand, S3Client } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { ulid } from 'ulid';
import type { PersonaRecord } from '@elderly-care/shared';
import { PollyAdapter, SageMakerTtsAdapter } from '../../tts/adapters.js';
import { TtsEngine } from '../../tts/engine.js';
import type { ConcreteLanguage } from '../../tts/types.js';
import { DynamoTable, Keys } from '../../db/index.js';
import type { GuardrailResult } from '../../guardrail/types.js';
import type { LlmGenerateResult } from '../../llm/types.js';

export interface TtsStageInput {
  elderId: string;
  traceId: string;
  llmResult: LlmGenerateResult;
  guardrailResult: GuardrailResult;
}

export interface TtsStageOutput {
  degraded: boolean;
  response: string;
  // Always present (never `undefined`) so Step Functions' JSONPath
  // ($.ttsResult.audioUrl in the ASL's Respond state) can always resolve
  // it — an absent JSON key fails path resolution, whereas `null` doesn't.
  audioUrl: string | null;
}

const PRESIGNED_URL_TTL_SECONDS = 600;

/** Step Functions Task target for the `tts_synthesize` node. */
export async function handler(input: TtsStageInput): Promise<TtsStageOutput> {
  const finalText = input.guardrailResult.allowed
    ? (input.guardrailResult.redactedContent ?? input.guardrailResult.safetyOverrideMessage ?? input.llmResult.replyText)
    : (input.guardrailResult.safetyOverrideMessage ?? '這個問題建議您諮詢醫師');

  const table = new DynamoTable();
  const persona = await table.getItem<PersonaRecord>(Keys.elderPk(input.elderId), Keys.personaSk());
  const preferredLanguage = persona?.preferredLanguage ?? 'zh-TW';
  // TTS has no "mixed" endpoint (unlike ASR's segment-level mixed-language
  // handling) — a mixed-language Persona falls back to Mandarin for replies.
  const language: ConcreteLanguage = preferredLanguage === 'mixed' ? 'zh-TW' : preferredLanguage;

  const engine = new TtsEngine({
    pollyAdapter: new PollyAdapter(),
    sageMakerAdapter: new SageMakerTtsAdapter(),
    traceId: input.traceId,
    elderId: input.elderId,
  });

  const outcome = await engine.synthesize(finalText, {
    language,
    speakingSpeed: persona?.speakingSpeed ?? 'normal',
  });

  if (outcome.degraded || !outcome.audio) {
    return { degraded: true, response: finalText, audioUrl: null };
  }

  const bucket = process.env.EXPORTS_BUCKET_NAME;
  if (!bucket) {
    return { degraded: true, response: finalText, audioUrl: null };
  }

  const key = `tts-replies/${input.elderId}/${ulid()}.mp3`;
  const s3 = new S3Client({});
  await s3.send(
    new PutObjectCommand({ Bucket: bucket, Key: key, Body: outcome.audio.audio, ContentType: outcome.audio.contentType }),
  );
  const audioUrl = await getSignedUrl(s3, new GetObjectCommand({ Bucket: bucket, Key: key }), {
    expiresIn: PRESIGNED_URL_TTL_SECONDS,
  }).catch(() => null);

  return { degraded: false, response: finalText, audioUrl };
}
