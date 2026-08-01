import type { Language } from '@elderly-care/shared';
import { getNodeConfig } from '../workflow/nodes.js';
import { RetryTracker, isRetryableError } from '../workflow/retry.js';
import { createErrorLog } from '../workflow/trace.js';
import { logError, recordStageMetric } from '../workflow/metrics.js';
import type { AsrAdapter } from './adapters.js';
import { ASK_TO_REPEAT_MESSAGE, isConfidenceAcceptable } from './confidence.js';
import { routeEndpoint } from './routing.js';
import type { AsrEndpoint, AudioInput, ConcreteLanguage, TranscriptSegment, TranscriptionResult } from './types.js';
import type { ASRConfig } from './types.js';

export interface AsrOutcome {
  degraded: boolean;
  message?: string;
  result?: TranscriptionResult;
}

export interface AsrEngineDeps {
  transcribeAdapter: AsrAdapter;
  sageMakerAdapter: AsrAdapter;
  traceId: string;
}

/**
 * ASREngine — routes by language (Property 1), applies the confidence gate
 * (Property 2), retries transient failures within the `asr` node's bounded
 * policy (Property 3), and logs endpoint/model/latency for every attempt
 * (A02.4) with PII-safe error logging on failure (Property 17).
 */
export class ASREngine {
  private readonly adaptersByEndpoint: Record<AsrEndpoint, AsrAdapter>;

  constructor(private readonly deps: AsrEngineDeps) {
    this.adaptersByEndpoint = {
      transcribe: deps.transcribeAdapter,
      sagemaker: deps.sageMakerAdapter,
    };
  }

  async transcribe(audio: AudioInput, config: ASRConfig): Promise<AsrOutcome> {
    const tracker = new RetryTracker();
    const policy = getNodeConfig('asr')!.retryPolicy;

    while (true) {
      try {
        const result =
          config.preferredLanguage === 'mixed'
            ? await this.transcribeMixed(audio, config)
            : await this.transcribeConcrete(audio, config, config.preferredLanguage as ConcreteLanguage);

        if (!isConfidenceAcceptable(result.confidence)) {
          return { degraded: true, message: ASK_TO_REPEAT_MESSAGE, result };
        }
        return { degraded: false, result };
      } catch (err) {
        const errorCode = err instanceof Error ? err.name : 'UnknownError';
        logError(
          createErrorLog({
            traceId: this.deps.traceId,
            component: 'asr',
            errorType: 'service_error',
            errorCode,
            message: err instanceof Error ? err.message : String(err),
            elderId: config.elderId,
            retryAttempt: tracker.getNodeAttempts('asr'),
            resolved: false,
            fallbackAction: 'asr_timeout',
          }),
        );

        const canRetry = isRetryableError(policy, errorCode) && tracker.recordFailureAndCheckRetry('asr', policy);
        if (!canRetry) {
          return { degraded: true, message: ASK_TO_REPEAT_MESSAGE };
        }
        await new Promise((resolve) => setTimeout(resolve, tracker.backoffSeconds(policy, 'asr') * 1000));
      }
    }
  }

  private async transcribeConcrete(
    audio: AudioInput,
    config: ASRConfig,
    language: ConcreteLanguage,
  ): Promise<TranscriptionResult> {
    const endpoint = routeEndpoint(language);
    const adapter = this.adaptersByEndpoint[endpoint];
    const start = Date.now();
    const adapterResult = await adapter.transcribe(audio, language);
    const latencyMs = Date.now() - start;

    await recordStageMetric({ component: 'asr', latencyMs, success: true });

    return {
      text: adapterResult.text,
      language,
      confidence: adapterResult.confidence,
      serviceEndpoint: endpoint,
      modelVersion: adapterResult.modelVersion,
      latencyMs,
      segments: adapterResult.segments,
    };
  }

  /**
   * Mixed-language strategy: transcribe the full utterance via AWS
   * Transcribe first (it covers Mandarin/English and returns per-segment
   * language hints), then re-transcribe any segment identified as
   * Hokkien/Hakka through the SageMaker endpoint, since Transcribe cannot
   * recognize those languages at all.
   */
  private async transcribeMixed(audio: AudioInput, config: ASRConfig): Promise<TranscriptionResult> {
    const start = Date.now();
    const primary = await this.transcribeConcrete(audio, config, 'zh-TW');

    const segments: TranscriptSegment[] = [];
    for (const segment of primary.segments) {
      if (routeEndpoint(segment.language as ConcreteLanguage) === 'sagemaker') {
        const reRouted = await this.adaptersByEndpoint.sagemaker.transcribe(audio, segment.language as 'nan-TW' | 'hak-TW');
        segments.push({ ...segment, text: reRouted.text, confidence: reRouted.confidence });
      } else {
        segments.push(segment);
      }
    }

    const combinedText = segments.map((s) => s.text).join('');
    const combinedConfidence = segments.length
      ? segments.reduce((sum, s) => sum + s.confidence, 0) / segments.length
      : primary.confidence;

    return {
      text: combinedText || primary.text,
      language: 'mixed' as Language,
      confidence: combinedConfidence,
      serviceEndpoint: 'transcribe+sagemaker',
      modelVersion: primary.modelVersion,
      latencyMs: Date.now() - start,
      segments,
    };
  }
}
