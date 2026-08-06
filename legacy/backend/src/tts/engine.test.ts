import { describe, expect, it } from 'vitest';
import type { TtsAdapter } from './adapters.js';
import { TtsEngine } from './engine.js';
import { routeTtsEndpoint } from './routing.js';

const okAdapter: TtsAdapter = {
  async synthesize() {
    return { audio: new Uint8Array([1, 2, 3]), contentType: 'audio/mpeg' };
  },
};

const failingAdapter: TtsAdapter = {
  async synthesize() {
    throw new Error('endpoint unreachable');
  },
};

describe('routeTtsEndpoint', () => {
  it('routes Mandarin/English to Polly and Hokkien/Hakka to SageMaker', () => {
    expect(routeTtsEndpoint('zh-TW')).toBe('polly');
    expect(routeTtsEndpoint('en-US')).toBe('polly');
    expect(routeTtsEndpoint('nan-TW')).toBe('sagemaker');
    expect(routeTtsEndpoint('hak-TW')).toBe('sagemaker');
  });
});

describe('TtsEngine.synthesize', () => {
  it('returns synthesized audio on success, tagged with the routed endpoint', async () => {
    const engine = new TtsEngine({
      pollyAdapter: okAdapter,
      sageMakerAdapter: failingAdapter,
      traceId: 't1',
      elderId: 'e1',
    });
    const result = await engine.synthesize('你好', { language: 'zh-TW', speakingSpeed: 'normal' });
    expect(result.degraded).toBe(false);
    expect(result.audio?.serviceEndpoint).toBe('polly');
  });

  it('degrades to text fallback instead of throwing when synthesis fails (A03.4)', async () => {
    const engine = new TtsEngine({
      pollyAdapter: failingAdapter,
      sageMakerAdapter: failingAdapter,
      traceId: 't1',
      elderId: 'e1',
    });
    const result = await engine.synthesize('你好', { language: 'zh-TW', speakingSpeed: 'normal' });
    expect(result.degraded).toBe(true);
    expect(result.textFallback).toBe('你好');
    expect(result.audio).toBeUndefined();
  });

  it('routes Hokkien text to the SageMaker adapter, not Polly', async () => {
    let pollyCalled = false;
    const trackedPolly: TtsAdapter = {
      async synthesize() {
        pollyCalled = true;
        return { audio: new Uint8Array(), contentType: 'audio/mpeg' };
      },
    };
    const engine = new TtsEngine({
      pollyAdapter: trackedPolly,
      sageMakerAdapter: okAdapter,
      traceId: 't1',
      elderId: 'e1',
    });
    const result = await engine.synthesize('你好', { language: 'nan-TW', speakingSpeed: 'normal' });
    expect(result.audio?.serviceEndpoint).toBe('sagemaker');
    expect(pollyCalled).toBe(false);
  });
});
