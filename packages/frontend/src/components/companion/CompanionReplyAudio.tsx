'use client';

import { SpeakerHigh, Stop } from '@phosphor-icons/react';
import { useEffect, useRef, useState } from 'react';
import type { CompanionTurn } from '@/lib/api/companion';
import { translate } from '@/lib/i18n/messages';
import { audioBase64ToObjectUrl, synthesizeSpeech } from '@/lib/voice/speech-gateway-client';
import styles from './CompanionReplyAudio.module.css';

type PlaybackState = 'idle' | 'loading' | 'playing' | 'ready' | 'failed';

/** Mount with a key for the elder and Agent run so audio never survives a new turn. */
export function CompanionReplyAudio({ turn }: { turn: CompanionTurn }) {
  const [state, setState] = useState<PlaybackState>('idle');
  const [notice, setNotice] = useState('');
  const mounted = useRef(false);
  const pending = useRef(false);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const objectUrl = useRef<string | null>(null);
  const t = (key: Parameters<typeof translate>[1]) => translate('zh-Hant', key);
  const language = turn.reply_language;
  const available =
    (language === 'zh-TW' || language === 'en-US') &&
    turn.transport_status === 'SYNTHESIS_CAPABILITY_ISSUED' &&
    !!turn.speech_synthesis_capability &&
    !!turn.speech_synthesis_text &&
    !!turn.speech_synthesis_expires_at;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current += 1;
      controller.current?.abort();
      if (audio.current) {
        audio.current.onended = null;
        audio.current.onerror = null;
        audio.current.pause();
        audio.current.removeAttribute('src');
      }
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    };
  }, []);

  async function play() {
    if (pending.current || !available || state === 'failed') return;
    if (language !== 'zh-TW' && language !== 'en-US') return;
    pending.current = true;
    const currentGeneration = ++generation.current;
    setNotice('');
    try {
      if (!audio.current) {
        const expiresAt = Date.parse(turn.speech_synthesis_expires_at ?? '');
        if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
          setState('failed');
          setNotice(t('companionAudio.expired'));
          return;
        }
        setState('loading');
        const abort = new AbortController();
        controller.current = abort;
        const timeout = window.setTimeout(() => abort.abort(), 35_000);
        let result;
        try {
          result = await synthesizeSpeech(
            turn.speech_synthesis_text!,
            language,
            turn.session_id,
            turn.agent_run_id,
            turn.speech_synthesis_capability!,
            'normal',
            abort.signal,
          );
        } finally {
          window.clearTimeout(timeout);
        }
        if (!mounted.current || currentGeneration !== generation.current) return;
        objectUrl.current = audioBase64ToObjectUrl(result.audioBase64, result.contentType);
        audio.current = new Audio(objectUrl.current);
        audio.current.onended = () => {
          if (mounted.current) setState('ready');
        };
        audio.current.onerror = () => {
          if (mounted.current) {
            setState('failed');
            setNotice(t('companionAudio.unavailable'));
          }
        };
      }
      audio.current.currentTime = 0;
      setState('playing');
      await audio.current.play();
    } catch (error) {
      if (!mounted.current || currentGeneration !== generation.current) return;
      if (
        audio.current &&
        (error instanceof DOMException || error instanceof Error) &&
        error.name === 'NotAllowedError'
      ) {
        setState('ready');
        setNotice(t('companionAudio.tapAgain'));
      } else {
        // The capability may already be consumed: never retry a synthesis or a companion turn.
        setState('failed');
        setNotice(t('companionAudio.unavailable'));
      }
    } finally {
      if (currentGeneration === generation.current) pending.current = false;
    }
  }

  function stop() {
    generation.current += 1;
    audio.current?.pause();
    pending.current = false;
    setState('ready');
  }

  if (!available) return <p className={styles.notice}>{t('companionAudio.textOnly')}</p>;

  return (
    <div className={styles.controls}>
      <button
        type="button"
        className={styles.button}
        disabled={state === 'loading' || state === 'failed'}
        aria-busy={state === 'loading'}
        onClick={state === 'playing' ? stop : () => void play()}
      >
        {state === 'playing' ? (
          <Stop size={32} weight="fill" aria-hidden="true" />
        ) : (
          <SpeakerHigh size={32} weight="fill" aria-hidden="true" />
        )}
        {t(
          state === 'loading'
            ? 'companionAudio.loading'
            : state === 'playing'
              ? 'companionAudio.stop'
              : state === 'ready'
                ? 'companionAudio.replay'
                : 'companionAudio.play',
        )}
      </button>
      <p role="status" className={styles.notice}>
        {notice ||
          (state === 'loading'
            ? t('companionAudio.loading')
            : state === 'playing'
              ? t('companionAudio.playing')
              : '')}
      </p>
    </div>
  );
}
