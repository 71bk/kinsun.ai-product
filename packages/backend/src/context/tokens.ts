/**
 * Deterministic token estimator (no live tokenizer call). CJK code points
 * are weighted ~1 token each; everything else ~0.25 tokens/char (~4
 * chars/token), which is the commonly cited ratio for English text.
 * Determinism matters more than exactness here — the same text must
 * always estimate to the same token count so budget packing is stable.
 */
export function estimateTokens(text: string): number {
  let tokens = 0;
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    const isCjk =
      (code >= 0x4e00 && code <= 0x9fff) || // CJK Unified Ideographs
      (code >= 0x3400 && code <= 0x4dbf) || // CJK Extension A
      (code >= 0x3000 && code <= 0x303f); // CJK punctuation
    tokens += isCjk ? 1 : 0.25;
  }
  return Math.ceil(tokens);
}
