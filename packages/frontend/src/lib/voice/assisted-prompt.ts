/** Fixed interface prompts only; never pass transcripts or AI replies to this API. */
export function playRetryPrompt(language: 'zh-TW' | 'en-US', signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  const synth = window.speechSynthesis;
  if (!synth) return Promise.reject(new Error('PROMPT_UNAVAILABLE'));
  const voice = synth.getVoices().find((item) => item.localService && item.lang.replace('_', '-') === language);
  if (!voice) return Promise.reject(new Error('PROMPT_UNAVAILABLE'));
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
