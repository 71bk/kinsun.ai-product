'use client';

/**
 * Local speech check UI.
 *
 * Verifies the browser -> Core ticket -> speech gateway -> Core ASR gate path
 * with a real microphone. It is a wiring check, not a product surface, and
 * deliberately uses the same consent and session state machine as the UI.
 *
 * This component performs no environment gating of its own: `page.tsx` is the
 * server boundary that returns 404 outside development. Keep it that way --
 * a client component cannot be trusted to withhold itself.
 */

import { useCallback, useRef, useState } from 'react';
import { BrowserVoiceRecorder } from '@/lib/voice/recorder';
import { transcribeTurn, VoiceTurnError } from '@/lib/voice/canonical-voice-turn';
import {
  audioBase64ToObjectUrl,
  canSynthesize,
  synthesizeSpeech,
  type SpeechLanguage,
} from '@/lib/voice/speech-gateway-client';

type Language = SpeechLanguage;

const LANGUAGES: { value: Language; label: string }[] = [
  { value: 'zh-TW', label: '國語 (Transcribe)' },
  { value: 'nan-TW', label: '台語 (SageMaker)' },
  { value: 'hak-TW', label: '客語 (SageMaker)' },
  { value: 'en-US', label: 'English (Transcribe)' },
];

export function DevSpeechView() {
  const recorderRef = useRef<BrowserVoiceRecorder | null>(null);
  const [language, setLanguage] = useState<Language>('zh-TW');
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [elderId, setElderId] = useState(process.env.NEXT_PUBLIC_DEMO_ELDER_ID ?? '');
  const [transcript, setTranscript] = useState('');
  const [gateDecision, setGateDecision] = useState('');
  const [error, setError] = useState('');
  const [ttsText, setTtsText] = useState('阿嬤您好，今天有沒有吃飯？');

  const start = useCallback(async () => {
    setError('');
    setTranscript('');
    setGateDecision('');
    if (elderId.trim() === '') {
      setError('enter a synthetic elder UUID before recording');
      return;
    }
    try {
      const recorder = recorderRef.current ?? new BrowserVoiceRecorder();
      recorderRef.current = recorder;
      await recorder.startRecording();
      setRecording(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'could not start recording');
    }
  }, [elderId]);

  const stop = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    setRecording(false);
    setBusy(true);
    try {
      const blob = await recorder.stopRecording();
      const result = await transcribeTurn(
        { apiBaseUrl: '/backend/core' },
        elderId.trim(),
        blob,
        language,
      );
      setTranscript(result.text);
      setGateDecision(result.decision);
    } catch (cause) {
      setError(
        cause instanceof VoiceTurnError && cause.stage === 'language'
          ? `${language}: no model deployed for this language`
          : cause instanceof Error
            ? cause.message
            : 'transcription failed',
      );
    } finally {
      setBusy(false);
    }
  }, [elderId, language]);

  const speak = useCallback(async () => {
    setError('');
    if (!canSynthesize(language)) {
      setError(`${language}: no TTS endpoint deployed for this language yet`);
      return;
    }
    setBusy(true);
    try {
      const result = await synthesizeSpeech(ttsText, language);
      const url = audioBase64ToObjectUrl(result.audioBase64, result.contentType);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'synthesis failed');
    } finally {
      setBusy(false);
    }
  }, [ttsText, language]);

  return (
    <main style={{ padding: 32, maxWidth: 720, fontFamily: 'system-ui, sans-serif' }}>
      <h1 style={{ fontSize: 24, marginBottom: 4 }}>Speech gateway check</h1>
      <p style={{ color: 'var(--color-muted-foreground)', marginBottom: 24 }}>
        Browser → Core Voice Ticket → speech-gateway → Core ASR Gate. Development only.
      </p>

      <label style={{ display: 'block', marginBottom: 24 }}>
        Synthetic elder UUID
        <input
          value={elderId}
          onChange={(event) => setElderId(event.target.value)}
          style={{ display: 'block', width: '100%', marginTop: 6, padding: 8 }}
        />
      </label>

      <fieldset
        style={{ marginBottom: 24, border: '1px solid var(--color-border-strong)', padding: 16 }}
      >
        <legend>Language</legend>
        {LANGUAGES.map((option) => (
          <label key={option.value} style={{ marginRight: 16, whiteSpace: 'nowrap' }}>
            <input
              type="radio"
              name="language"
              value={option.value}
              checked={language === option.value}
              onChange={() => setLanguage(option.value)}
            />{' '}
            {option.label}
          </label>
        ))}
        {!canSynthesize(language) && (
          <p style={{ margin: '12px 0 0', color: 'var(--color-muted-foreground)', fontSize: 14 }}>
            ASR only — no TTS endpoint is deployed for this language.
          </p>
        )}
      </fieldset>

      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18 }}>ASR — speak into the microphone</h2>
        <button
          type="button"
          onClick={recording ? stop : start}
          disabled={busy}
          style={{
            padding: '12px 24px',
            fontSize: 16,
            background: recording ? 'var(--color-destructive)' : 'var(--color-accent-text)',
            color: 'var(--color-on-accent)',
            border: 'none',
            borderRadius: 6,
            cursor: busy ? 'wait' : 'pointer',
          }}
        >
          {recording ? '停止並辨識' : busy ? '處理中…' : '開始錄音'}
        </button>

        {transcript !== '' && (
          <div
            style={{
              marginTop: 16,
              padding: 16,
              background: 'var(--color-surface)',
              borderRadius: 6,
            }}
          >
            <p style={{ margin: 0, fontSize: 18 }}>{transcript}</p>
            <p style={{ margin: '8px 0 0', color: 'var(--color-muted-foreground)', fontSize: 14 }}>
              trusted Core decision: {gateDecision}
            </p>
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: 18 }}>TTS — synthesize and play</h2>
        <textarea
          value={ttsText}
          onChange={(event) => setTtsText(event.target.value)}
          rows={3}
          style={{ width: '100%', padding: 8, fontSize: 15, fontFamily: 'inherit' }}
        />
        <button
          type="button"
          onClick={speak}
          disabled={busy || ttsText.trim() === ''}
          style={{
            marginTop: 8,
            padding: '12px 24px',
            fontSize: 16,
            background: 'var(--color-primary-strong)',
            color: 'var(--color-on-primary)',
            border: 'none',
            borderRadius: 6,
            cursor: busy ? 'wait' : 'pointer',
          }}
        >
          {busy ? '處理中…' : '播放'}
        </button>
      </section>

      {error !== '' && (
        <p style={{ marginTop: 24, color: 'var(--color-destructive)' }} role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
