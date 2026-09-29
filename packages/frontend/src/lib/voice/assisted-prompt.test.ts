import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { playRetryPrompt } from './assisted-prompt';

class Prompt {
  voice: SpeechSynthesisVoice | null = null;
  lang = '';
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly text: string) {}
}

let voices: SpeechSynthesisVoice[];
let synth: EventTarget & {
  getVoices: ReturnType<typeof vi.fn>;
  speak: ReturnType<typeof vi.fn>;
  cancel: ReturnType<typeof vi.fn>;
};
const local = { localService: true, lang: 'zh_TW' } as SpeechSynthesisVoice;

beforeEach(() => {
  vi.useFakeTimers();
  voices = [];
  synth = Object.assign(new EventTarget(), {
    getVoices: vi.fn(() => voices),
    speak: vi.fn((prompt: Prompt) => { prompt.onend?.(); }),
    cancel: vi.fn(),
  });
  vi.stubGlobal('window', { speechSynthesis: synth });
  vi.stubGlobal('SpeechSynthesisUtterance', Prompt);
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('fixed local retry prompt', () => {
  it('waits for initially empty voices and plays the fixed prompt once', async () => {
    const result = playRetryPrompt('zh-TW', new AbortController().signal);
    expect(synth.speak).not.toHaveBeenCalled();
    voices = [local];
    synth.dispatchEvent(new Event('voiceschanged'));
    await result;
    expect(synth.speak).toHaveBeenCalledTimes(1);
    expect(synth.speak.mock.calls[0][0]).toMatchObject({
      voice: local, text: '剛才沒有聽清楚，請慢慢再說一次。', lang: 'zh-TW',
    });
    synth.dispatchEvent(new Event('voiceschanged'));
    expect(synth.speak).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('uses an already loaded local voice without waiting', async () => {
    voices = [local];
    await playRetryPrompt('zh-TW', new AbortController().signal);
    expect(synth.speak).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('never falls back to a remote voice or the wrong language', async () => {
    voices = [{ ...local, localService: false }, { ...local, lang: 'en-US' }];
    const result = expect(playRetryPrompt('zh-TW', new AbortController().signal))
      .rejects.toThrow('PROMPT_UNAVAILABLE');
    await vi.advanceTimersByTimeAsync(2_000);
    await result;
    voices = [local];
    synth.dispatchEvent(new Event('voiceschanged'));
    expect(synth.speak).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('aborts while voices load and cannot speak after cancellation', async () => {
    const controller = new AbortController();
    const result = expect(playRetryPrompt('zh-TW', controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();
    await result;
    voices = [local];
    synth.dispatchEvent(new Event('voiceschanged'));
    expect(synth.speak).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('stops an active prompt on cancellation and clears its timeout', async () => {
    voices = [local];
    synth.speak.mockImplementation(() => undefined);
    const controller = new AbortController();
    const result = expect(playRetryPrompt('zh-TW', controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    await Promise.resolve();
    expect(synth.speak).toHaveBeenCalledTimes(1);
    controller.abort();
    await result;
    expect(synth.cancel).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
