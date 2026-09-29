function localVoice(
  synth: SpeechSynthesis, language: 'zh-TW' | 'en-US', signal: AbortSignal,
): Promise<SpeechSynthesisVoice> {
  return new Promise((resolve, reject) => {
    const finish = (voice?: SpeechSynthesisVoice, error?: Error) => {
      clearTimeout(timer);
      synth.removeEventListener('voiceschanged', check);
      signal.removeEventListener('abort', abort);
      if (voice) resolve(voice);
      else reject(error ?? new Error('PROMPT_UNAVAILABLE'));
    };
    const check = () => {
      const voice = synth.getVoices().find((item) =>
        item.localService && item.lang.replace('_', '-') === language);
      if (voice) finish(voice);
    };
    const abort = () => finish(undefined, new DOMException('Cancelled', 'AbortError'));
    // Browsers initially return [] while loading their installed voices.
    // Wait briefly for that list, retaining the local-only language requirement.
    const timer = setTimeout(() => finish(), 2_000);
    synth.addEventListener('voiceschanged', check);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort(); else check();
  });
}

/** Fixed interface prompts only; never pass transcripts or AI replies to this API. */
export async function playRetryPrompt(language: 'zh-TW' | 'en-US', signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  const synth = window.speechSynthesis;
  if (!synth) return Promise.reject(new Error('PROMPT_UNAVAILABLE'));
  const voice = await localVoice(synth, language, signal);
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const prompt = new SpeechSynthesisUtterance(language === 'zh-TW'
      ? '剛才沒有聽清楚，請慢慢再說一次。'
      : "I didn't hear that clearly. Please say it again slowly.");
    prompt.voice = voice;
    prompt.lang = language;
    prompt.rate = 0.85;
    const finish = (error?: Error) => {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
      prompt.onend = null; prompt.onerror = null;
      if (error) { synth.cancel(); reject(error); } else resolve();
    };
    const abort = () => finish(new DOMException('Cancelled', 'AbortError'));
    const timer = setTimeout(() => finish(new Error('PROMPT_UNAVAILABLE')), 12_000);
    signal.addEventListener('abort', abort, { once: true });
    prompt.onend = () => finish();
    prompt.onerror = () => finish(new Error('PROMPT_UNAVAILABLE'));
    synth.speak(prompt);
  });
}
