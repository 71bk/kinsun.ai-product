'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ApiConfig } from '@/lib/api/client';
import { confirmAsrGate } from '@/lib/api/companion';
import type { CompanionTurn } from '@/lib/api/companion';
import { translate } from '@/lib/i18n/messages';
import { BrowserVoiceRecorder } from '@/lib/voice/recorder';
import { speakTurn, transcribeTurn, VoiceTurnError } from '@/lib/voice/canonical-voice-turn';
import type { SpeechLanguage } from '@/lib/voice/speech-gateway-client';
import { CompanionCharacter, type ConversationState } from './CompanionCharacter';
import { LanguageSelect } from './LanguageSelect';
import { readDevPreviewState } from './dev-preview';
import { LowConfidenceCard } from './LowConfidenceCard';
import { MicPermissionGuide } from './MicPermissionGuide';
import { RecordButton } from './RecordButton';
import { VoiceMemoryReceipt } from './VoiceMemoryReceipt';
import { STATE_COPY, type VoicePageState } from './voice-page-state';
import styles from './VoiceInteractionPanel.module.css';

const DEFAULT_GREETING = '你好啊！今天想聊什麼呢？';

/** §10.1 Timeout: nothing came back after we said we were listening. */
const ASR_TIMEOUT_MS = 10_000;

/** Placeholder shown only by the dev preview, so the card has something to quote. */
const PREVIEW_TRANSCRIPT = '我今天早上有吃藥';

/** States where a turn is in flight, so the language must not be swapped. */
const busyStates = new Set<VoicePageState>([
  'processingAsr',
  'lowConfidence',
  'generating',
  'playing',
]);

/** Maps the page state onto the companion's presentation states. */
function toConversationState(state: VoicePageState): ConversationState {
  switch (state) {
    case 'recording':
      return 'listening';
    case 'processingAsr':
    case 'generating':
    case 'lowConfidence':
      return 'processing';
    case 'playing':
      return 'speaking';
    case 'offline':
    case 'permissionDenied':
    case 'timeout':
      return 'sleeping';
    default:
      return 'idle';
  }
}

export interface VoiceInteractionPanelProps {
  /** Elder hasn't granted recording consent yet — disables the mic entirely (A06.2). */
  consentGranted: boolean;
  /** Same-origin BFF config; the panel never holds a bearer token itself. */
  apiConfig: ApiConfig;
  elderId: string;
}

export function VoiceInteractionPanel({
  apiConfig,
  elderId,
  consentGranted,
}: VoiceInteractionPanelProps) {
  const [state, setState] = useState<VoicePageState>('idle');
  const [previewState, setPreviewState] = useState<VoicePageState | null>(null);
  const [displayText, setDisplayText] = useState('');
  const [transcript, setTranscript] = useState('');
  const [pendingTranscript, setPendingTranscript] = useState('');
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
  const [errorText, setErrorText] = useState('');
  const [noticeText, setNoticeText] = useState('');
  const [language, setLanguage] = useState<SpeechLanguage>('zh-TW');
  const [memoryUpdates, setMemoryUpdates] = useState<NonNullable<CompanionTurn['memory_updates']>>(
    [],
  );
  const generation = useRef(0);

  const recorderRef = useRef<BrowserVoiceRecorder | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const asrAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setPreviewState(readDevPreviewState());
  }, []);

  const isPreview = previewState !== null;
  const effectiveState: VoicePageState = previewState ?? state;

  /** §10.1 Offline — derived client-side from the browser, not from the server. */
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!window.navigator.onLine) setState('offline');

    const handleOffline = () => setState('offline');
    const handleOnline = () => setState((current) => (current === 'offline' ? 'idle' : current));

    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);
    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
    };
  }, []);

  /** §10.1 Timeout — a local timer, the server sends no such signal. */
  useEffect(() => {
    if (state !== 'processingAsr') return;
    const timer = window.setTimeout(() => {
      setState((current) => {
        if (current !== 'processingAsr') return current;
        asrAbortRef.current?.abort();
        return 'timeout';
      });
    }, ASR_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [state]);

  useEffect(() => {
    if (!consentGranted) return;
    // Preview renders states only — no microphone, no recording.
    if (isPreview) return;
    recorderRef.current = new BrowserVoiceRecorder();
  }, [consentGranted, isPreview, apiConfig, elderId]);

  // Drop scoped receipts and late responses when the account/consent changes.
  useEffect(() => {
    setMemoryUpdates([]);
    setDisplayText('');
    setTranscript('');
    setPendingTranscript('');
    setPendingSessionId(null);
    setErrorText('');
    setNoticeText('');
    setState('idle');
    return () => {
      generation.current += 1;
      asrAbortRef.current?.abort();
      recorderRef.current?.dispose();
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    };
  }, [apiConfig, elderId, consentGranted]);

  /**
   * Sends confirmed text to Core and plays the spoken reply.
   *
   * Only reached with a transcript the elder either spoke clearly or explicitly
   * confirmed — recognition alone never triggers this.
   */
  const runCompanion = useCallback(
    async (sessionId: string, confirmedText: string) => {
      const currentGeneration = generation.current;
      setState('generating');
      try {
        const reply = await speakTurn(apiConfig, sessionId, confirmedText, language);
        if (currentGeneration !== generation.current) {
          if (reply.audioUrl) URL.revokeObjectURL(reply.audioUrl);
          return;
        }
        setDisplayText(reply.replyText);
        setMemoryUpdates(reply.memoryUpdates ?? []);

        if (reply.textOnlyByLanguage) {
          // Said explicitly rather than leaving the elder waiting for a voice
          // that is never coming.
          setNoticeText('這個語言的回答目前只能用文字顯示。');
        }

        if (reply.audioUrl) {
          if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
          audioUrlRef.current = reply.audioUrl;
          setState('playing');
          try {
            await recorderRef.current?.playAudioFromUrl(reply.audioUrl);
          } catch {
            // Core may already have saved memory: playback cannot undo that fact.
            if (currentGeneration === generation.current) {
              setNoticeText(translate('zh-Hant', 'companionAudio.unavailable'));
            }
          }
        }
        if (currentGeneration === generation.current) setState('idle');
      } catch (cause) {
        if (currentGeneration !== generation.current) return;
        setErrorText(
          cause instanceof VoiceTurnError && cause.stage === 'companion'
            ? translate('zh-Hant', 'voiceMemory.turnUnavailable')
            : '目前無法開始這次對話，請稍後再試。',
        );
        setState('idle');
      }
    },
    [apiConfig, language],
  );

  const beginRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;

    const granted = recorder.hasMicPermission() || (await recorder.requestMicPermission());
    if (!granted) {
      setState('permissionDenied');
      return;
    }
    setDisplayText('');
    setMemoryUpdates([]);
    setTranscript('');
    setPendingTranscript('');
    setPendingSessionId(null);
    setErrorText('');
    setNoticeText('');
    await recorder.startRecording();
    setState('recording');
  }, []);

  const handlePress = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;

    if (state === 'idle' || state === 'timeout' || state === 'permissionDenied') {
      await beginRecording();
      return;
    }

    if (state !== 'recording') return;

    const blob = await recorder.stopRecording();
    setState('processingAsr');
    const asrController = new AbortController();
    asrAbortRef.current?.abort();
    asrAbortRef.current = asrController;
    try {
      const result = await transcribeTurn(apiConfig, elderId, blob, language, asrController.signal);
      if (asrController.signal.aborted) return;
      asrAbortRef.current = null;
      if (result.decision === 'CONFIRMATION_REQUIRED') {
        if (result.text.trim() === '') {
          setErrorText('剛剛沒有聽到聲音，請再說一次。');
          setState('idle');
          return;
        }
        setPendingTranscript(result.text);
        setPendingSessionId(result.sessionId);
        setState('lowConfidence');
        return;
      }
      if (result.decision !== 'CAN_SEND_TO_AGENT') {
        setErrorText('這次語音無法安全處理，請再說一次。');
        setState('idle');
        return;
      }
      setTranscript(result.text);
      await runCompanion(result.sessionId, result.text);
    } catch (cause) {
      if (asrController.signal.aborted) return;
      asrAbortRef.current = null;
      const stage = cause instanceof VoiceTurnError ? cause.stage : null;
      setErrorText(
        stage === 'language'
          ? // Not "please repeat": repeating cannot help when no model exists.
            '這個語言目前還沒辦法辨識，請先改用國語。'
          : stage === 'transcription'
            ? '目前無法辨識語音，請稍後再試。'
            : '目前無法處理這次語音，請稍後再試。',
      );
      setState('idle');
    }
  }, [state, beginRecording, runCompanion, language, apiConfig, elderId]);

  // The three handlers also drop any preview override, so the full-screen card
  // stays dismissible when a reviewer opened it via ?previewState=lowConfidence.
  const handleConfirmTranscript = useCallback(async () => {
    const currentGeneration = generation.current;
    setPreviewState(null);
    const confirmed = pendingTranscript;
    const sessionId = pendingSessionId;
    if (confirmed.trim() === '' || sessionId === null) {
      setState('idle');
      return;
    }
    try {
      const decision = await confirmAsrGate(apiConfig, sessionId, 'CONFIRM');
      if (currentGeneration !== generation.current) return;
      if (decision.decision !== 'CAN_SEND_TO_AGENT') {
        setErrorText('確認已逾時，請再說一次。');
        setState('idle');
        return;
      }
    } catch {
      if (currentGeneration !== generation.current) return;
      setErrorText('目前無法確認這段語音，請再說一次。');
      setState('idle');
      return;
    }
    setTranscript(confirmed);
    setPendingTranscript('');
    setPendingSessionId(null);
    await runCompanion(sessionId, confirmed);
  }, [apiConfig, pendingSessionId, pendingTranscript, runCompanion]);

  const rejectPendingTranscript = useCallback(async () => {
    const sessionId = pendingSessionId;
    if (sessionId !== null) {
      try {
        await confirmAsrGate(apiConfig, sessionId, 'REJECT');
      } catch {
        // No Agent call follows a rejection. If Core is unavailable, the short
        // evidence TTL still prevents the pending transcript from being used.
      }
    }
    setPendingSessionId(null);
    setPendingTranscript('');
    setTranscript('');
    setState('idle');
  }, [apiConfig, pendingSessionId]);

  const handleRetryTranscript = useCallback(() => {
    setPreviewState(null);
    void rejectPendingTranscript();
  }, [rejectPendingTranscript]);

  const handleDeferTranscript = useCallback(() => {
    setPreviewState(null);
    void rejectPendingTranscript();
  }, [rejectPendingTranscript]);

  // The consent gate exists to stop recording without consent. The dev preview
  // records nothing: the effect above returns before constructing any
  // BrowserVoiceRecorder or VoiceWebSocketClient when isPreview, so no
  // microphone is opened and no audio leaves the page. Exempting it therefore
  // gives up no protection, and the gate still applies in full to every
  // non-preview render (and to all of production, where isPreview is always
  // false — see dev-preview.tsx).
  if (!consentGranted && !isPreview) {
    return <p className={styles.muted}>請先完成錄音同意設定，才能開始使用語音功能。</p>;
  }

  const companionMessage =
    effectiveState === 'idle' || effectiveState === 'playing'
      ? displayText || DEFAULT_GREETING
      : STATE_COPY[effectiveState];

  const cardTranscript = pendingTranscript || (isPreview ? PREVIEW_TRANSCRIPT : '');

  return (
    <section className={styles.panel} aria-label="語音陪伴">
      <div className={styles.companionArea}>
        <CompanionCharacter
          state={toConversationState(effectiveState)}
          message={companionMessage}
        />
      </div>

      <div className={styles.controlArea}>
        <LanguageSelect
          language={language}
          onChange={setLanguage}
          // Changing language mid-turn would leave an utterance being transcribed
          // by one model and attributed to another.
          disabled={effectiveState === 'recording' || busyStates.has(effectiveState)}
        />

        <RecordButton state={effectiveState} onPress={handlePress} />

        {/* §1 狀態可感知 / §13 — the state is text, not only motion, and it is announced. */}
        <p aria-live="polite" className={styles.stateMessage}>
          {STATE_COPY[effectiveState]}
        </p>

        {effectiveState === 'permissionDenied' && <MicPermissionGuide onRetry={handlePress} />}

        {errorText !== '' && (
          <p className={styles.error} role="alert">
            {errorText}
          </p>
        )}

        {/* Not an error — the reply arrived, it just cannot be spoken yet. */}
        {noticeText !== '' && errorText === '' && (
          <p aria-live="polite" className={styles.notice}>
            {noticeText}
          </p>
        )}

        {transcript && <p className={styles.transcript}>您說：「{transcript}」</p>}
        {memoryUpdates.map((memory) => (
          <VoiceMemoryReceipt
            key={`${elderId}:${memory.memory_id}:${memory.version}`}
            apiConfig={apiConfig}
            elderId={elderId}
            memory={memory}
          />
        ))}
      </div>

      {effectiveState === 'lowConfidence' && cardTranscript !== '' && (
        <LowConfidenceCard
          transcript={cardTranscript}
          onConfirm={handleConfirmTranscript}
          onRetry={handleRetryTranscript}
          onDefer={handleDeferTranscript}
        />
      )}
    </section>
  );
}
