import { createErrorLog } from '../workflow/trace.js';
import { logError, recordStageMetric } from '../workflow/metrics.js';
import type { TtsAdapter } from './adapters.js';
import { routeTtsEndpoint } from './routing.js';
import type { TtsConfig, TtsEndpoint, TtsOutcome } from './types.js';

export interface TtsEngineDeps {
  pollyAdapter: TtsAdapter;
  sageMakerAdapter: TtsAdapter;
  traceId: string;
  elderId: string;
}

/**
 * TtsEngine (A03.2-A03.4) — routes by Persona language, and on any
 * synthesis failure degrades to a text-only outcome instead of throwing, so
 * the elder always sees a reply even when speech synthesis is unavailable.
 */
export class TtsEngine {
  private readonly adaptersByEndpoint: Record<TtsEndpoint, TtsAdapter>;

  constructor(private readonly deps: TtsEngineDeps) {
    this.adaptersByEndpoint = { polly: deps.pollyAdapter, sagemaker: deps.sageMakerAdapter };
  }

  async synthesize(text: string, config: TtsConfig): Promise<TtsOutcome> {
    const endpoint = routeTtsEndpoint(config.language);
    const adapter = this.adaptersByEndpoint[endpoint];
    const start = Date.now();

    try {
      const result = await adapter.synthesize(text, config.language, config.speakingSpeed);
      const latencyMs = Date.now() - start;
      await recordStageMetric({ component: 'tts', latencyMs, success: true });
      return {
        degraded: false,
        audio: { audio: result.audio, contentType: result.contentType, serviceEndpoint: endpoint, latencyMs },
      };
    } catch (err) {
      const errorCode = err instanceof Error ? err.name : 'UnknownError';
      logError(
        createErrorLog({
          traceId: this.deps.traceId,
          component: 'tts',
          errorType: 'service_error',
          errorCode,
          message: err instanceof Error ? err.message : String(err),
          elderId: this.deps.elderId,
          retryAttempt: 0,
          resolved: false,
          fallbackAction: 'tts_failure',
        }),
      );
      await recordStageMetric({ component: 'tts', latencyMs: Date.now() - start, success: false });
      return { degraded: true, textFallback: text };
    }
  }
}
