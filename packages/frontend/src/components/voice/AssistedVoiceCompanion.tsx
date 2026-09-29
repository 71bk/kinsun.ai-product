'use client';

import { useEffect, useRef, useState } from 'react';
import { getCurrentTabletSession } from '@/lib/api/assisted-elders';
import { runAssistedVoiceTurn } from '@/lib/voice/assisted-voice-turn';
import { HandsFreeRecorder } from '@/lib/voice/hands-free-recorder';
import { playRetryPrompt } from '@/lib/voice/assisted-prompt';
import styles from './AssistedVoiceCompanion.module.css';

type Phase = 'idle' | 'preparing' | 'listening' | 'processing' | 'playing';
const LABEL: Record<Phase, string> = {
  idle: '準備好後，由照服員開啟語音', preparing: '正在準備麥克風…',
  listening: '我在聽，請慢慢說', processing: '小暖正在想怎麼回覆…', playing: '小暖正在說話',
};

export function AssistedVoiceCompanion({ assistedSessionId, onEnd, onReply, onActiveChange }: {
  assistedSessionId: string; onEnd: () => Promise<void>;
  onReply: (text: string) => void; onActiveChange: (active: boolean) => void;
}) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [language, setLanguage] = useState<'zh-TW' | 'en-US'>('zh-TW');
  const [notice, setNotice] = useState('');
  const controller = useRef<AbortController | null>(null);
  const recorder = useRef<HandsFreeRecorder | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const callbacks = useRef({ onEnd, onReply, onActiveChange });
  callbacks.current = { onEnd, onReply, onActiveChange };

  function halt() {
    controller.current?.abort();
    controller.current = null;
    audio.current?.pause();
    recorder.current?.dispose();
    recorder.current = null;
  }
  useEffect(() => () => { halt(); callbacks.current.onActiveChange(false); }, []);

  async function play(url: string, signal: AbortSignal) {
    signal.throwIfAborted();
    const player = new Audio(url);
    audio.current = player;
    try {
      await new Promise<void>((resolve, reject) => {
        const abort = () => { player.pause(); reject(new DOMException('Cancelled', 'AbortError')); };
        signal.addEventListener('abort', abort, { once: true });
        const done = (error?: Error) => {
          signal.removeEventListener('abort', abort);
          if (error) reject(error); else resolve();
        };
        player.onended = () => done();
        player.onerror = () => done(new Error('PLAYBACK_FAILED'));
        void player.play().catch(() => done(new Error('PLAYBACK_FAILED')));
      });
    } finally {
      player.pause();
      player.removeAttribute('src');
      audio.current = null;
    }
  }

  async function start() {
    if (controller.current) return;
    const run = new AbortController();
    controller.current = run;
    const device = new HandsFreeRecorder();
    recorder.current = device;
    callbacks.current.onActiveChange(true);
    setPhase('preparing'); setNotice('');
    let opened = false;
    let emptyAttempts = 0;
    try {
      await device.open();
      opened = true;
      for (let turn = 0; turn < 12; turn += 1) {
        run.signal.throwIfAborted();
        const current = await getCurrentTabletSession();
        run.signal.throwIfAborted();
        if (current.assisted_session_id !== assistedSessionId || current.first_use_acknowledgement.status !== 'ACKNOWLEDGED') {
          throw new Error('SESSION_UNAVAILABLE');
        }
        setPhase('listening');
        const recording = await device.capture(run.signal);
        run.signal.throwIfAborted();
        if (!recording) {
          emptyAttempts += 1;
          if (emptyAttempts >= 2) { setNotice('暫時沒有聽到說話，麥克風已暫停。請照服員協助重新開啟。'); break; }
          continue;
        }
        setPhase('processing');
        const result = await runAssistedVoiceTurn(recording, language, run.signal);
        if (run.signal.aborted) {
          if (result.kind === 'reply' && result.audioUrl) URL.revokeObjectURL(result.audioUrl);
          run.signal.throwIfAborted();
        }
        if (result.kind === 'stop') {
          halt();
          await callbacks.current.onEnd();
          return;
        }
        if (result.kind === 'retry') {
          emptyAttempts += 1;
          setNotice('剛才沒有聽清楚，請慢慢再說一次。');
          if (emptyAttempts >= 2) { setNotice('連續未聽清楚，麥克風已暫停。請照服員協助。'); break; }
          await playRetryPrompt(language, run.signal);
          continue;
        }
        emptyAttempts = 0;
        callbacks.current.onReply(result.text);
        if (!result.audioUrl) { setNotice('回覆已顯示，但目前無法播放語音。麥克風已暫停，請照服員協助。'); break; }
        setNotice(''); setPhase('playing');
        try { await play(result.audioUrl, run.signal); }
        finally { URL.revokeObjectURL(result.audioUrl); }
        if (turn === 11) setNotice('已完成這次陪伴，麥克風已暫停。請照服員確認後再開啟。');
      }
    } catch {
      if (!run.signal.aborted) setNotice(opened
        ? '語音或連線目前無法使用，麥克風已暫停。請照服員檢查後再試。'
        : '無法使用麥克風。請照服員確認瀏覽器允許收音，並使用 HTTPS 或本機連線。');
    } finally {
      device.dispose();
      if (controller.current === run) {
        controller.current = null;
        recorder.current = null;
      }
      if (!run.signal.aborted) { setPhase('idle'); callbacks.current.onActiveChange(false); }
    }
  }

  return <section className={styles.panel} aria-label="語音陪伴">
    <p className={styles.status} role="status">{LABEL[phase]}</p>
    {phase === 'idle' ? <>
      <label>對話語言 <select value={language} onChange={(event) => setLanguage(event.target.value as 'zh-TW' | 'en-US')}>
        <option value="zh-TW">華語</option><option value="en-US">English</option>
      </select></label>
      <button className={styles.start} type="button" onClick={() => void start()}>開啟語音陪伴</button>
      <p>由照服員開啟後，直接說話即可。說完稍停，小暖就會回覆；回覆後會繼續聽。</p>
    </> : <button className={styles.stop} type="button" onClick={() => {
      halt(); setPhase('idle'); setNotice('麥克風與播放已暫停。'); callbacks.current.onActiveChange(false);
    }}>暫停收音與播放</button>}
    <p>想結束時，請在小暖聆聽時說「停止」，或請照服員協助結束。</p>
    {notice && <p role="alert">{notice}</p>}
  </section>;
}
