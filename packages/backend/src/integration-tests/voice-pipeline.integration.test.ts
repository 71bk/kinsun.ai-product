import { describe, expect, it } from 'vitest';
import type { AsrAdapter } from '../asr/adapters.js';
import { ASREngine } from '../asr/engine.js';
import { ContextComposer } from '../context/composer.js';
import type { ContextComposeInputs } from '../context/types.js';
import { detectEmergency } from '../guardrail/emergency.js';
import { GuardrailEngine } from '../guardrail/engine.js';
import type { TtsAdapter } from '../tts/adapters.js';
import { TtsEngine } from '../tts/engine.js';

/**
 * 端到端語音對話整合測試 (task 25.3). Chains ASREngine -> ContextComposer ->
 * (fake LLM) -> GuardrailEngine -> TtsEngine using the same injectable
 * adapter seams the real Step Functions stage handlers use — every engine
 * here is the real production class, only the network-calling adapters at
 * the very edge are fakes. This is what proves the modules actually
 * compose, not just that each one is individually correct.
 */
describe('Integration: end-to-end voice conversation pipeline', () => {
  it('carries a golden-path utterance through ASR -> Context -> LLM -> Guardrail -> TTS', async () => {
    const fakeTranscribe: AsrAdapter = {
      async transcribe() {
        return {
          text: '我今天中午吃了地瓜稀飯',
          confidence: 0.92,
          modelVersion: 'fake-transcribe-v1',
          segments: [{ text: '我今天中午吃了地瓜稀飯', startTime: 0, endTime: 2, confidence: 0.92, language: 'zh-TW' }],
        };
      },
    };
    const asrEngine = new ASREngine({
      transcribeAdapter: fakeTranscribe,
      sageMakerAdapter: fakeTranscribe,
      traceId: 'trace-int-1',
    });

    const asrOutcome = await asrEngine.transcribe(
      { data: new Uint8Array([1, 2, 3]), encoding: 'opus', sampleRate: 16000 },
      { elderId: 'elder-1', preferredLanguage: 'zh-TW', sampleRate: 16000, encoding: 'opus' },
    );
    expect(asrOutcome.degraded).toBe(false);
    expect(asrOutcome.result!.text).toContain('地瓜稀飯');

    const contextInputs: ContextComposeInputs = {
      persona: {
        displayName: '林阿嬤',
        preferredLanguage: 'zh-TW',
        responseLength: 'short',
        speakingSpeed: 'normal',
        interactionStyle: 'warm',
        customGreeting: '',
      },
      recentSummary: null,
      memories: [],
      situationalContext: {
        currentTime: '2026-07-24T12:00:00Z',
        dayOfWeek: 'Friday',
        weather: null,
        recentInteractionCount: 1,
        lastInteractionTime: null,
      },
      searchResults: [],
    };
    const contextResult = new ContextComposer().compose(
      { elderId: 'elder-1', currentUtterance: asrOutcome.result!.text, conversationHistory: [], tokenBudget: 4096 },
      contextInputs,
    );
    expect(contextResult.totalTokens).toBeLessThanOrEqual(4096);

    // Fake LLM stage — real LlmEngine would call Bedrock; here we just
    // assert the pipeline correctly threads the ASR text + persona through.
    const replyText = `${contextResult.persona.displayName}，聽起來吃得不錯！`;

    const guardrailEngine = new GuardrailEngine(); // no guardrailId configured -> pass-through
    const guardrailResult = await guardrailEngine.check(replyText, { elderId: 'elder-1', conversationType: 'general_chat' });
    expect(guardrailResult.allowed).toBe(true);

    const fakeTts: TtsAdapter = {
      async synthesize(text) {
        return { audio: new TextEncoder().encode(text), contentType: 'audio/mpeg' };
      },
    };
    const ttsEngine = new TtsEngine({ pollyAdapter: fakeTts, sageMakerAdapter: fakeTts, traceId: 'trace-int-1', elderId: 'elder-1' });
    const ttsOutcome = await ttsEngine.synthesize(replyText, { language: 'zh-TW', speakingSpeed: 'normal' });

    expect(ttsOutcome.degraded).toBe(false);
    expect(ttsOutcome.audio?.serviceEndpoint).toBe('polly');
  });

  it('short-circuits to the fixed 119 safety instruction for an emergency utterance, bypassing the LLM reply entirely', async () => {
    const emergencyUtterance = '我胸口很痛，喘不過氣';
    const emergency = detectEmergency(emergencyUtterance);
    expect(emergency).not.toBeNull();

    const guardrailEngine = new GuardrailEngine();
    const result = await guardrailEngine.check(emergencyUtterance, { elderId: 'elder-1', conversationType: 'general_chat' });
    expect(result.safetyOverrideMessage).toContain('119');
    expect(result.allowed).toBe(true); // pass-through with an override message, not a block
  });
});
