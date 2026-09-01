'use client';

import { ChatCircleDots, PaperPlaneTilt, ShieldCheck, SignOut } from '@phosphor-icons/react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type FormEvent, useEffect, useState } from 'react';
import {
  endTabletSession,
  getCurrentTabletSession,
  runAssistedCompanionTurn,
  type TabletSession,
} from '@/lib/api/assisted-elders';
import styles from './ElderSessionPage.module.css';

interface ChatMessage {
  id: string;
  role: 'elder' | 'assistant';
  text: string;
}
export default function ElderSessionPage() {
  const router = useRouter();
  const [session, setSession] = useState<TabletSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getCurrentTabletSession()
      .then((current) => {
        if (!cancelled) setSession(current);
      })
      .catch(() => {
        if (!cancelled) setSession(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'elder', text }]);
    setInput('');
    setBusy(true);
    setError(false);
    try {
      const turn = await runAssistedCompanionTurn(text);
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'assistant', text: turn.reply_text },
      ]);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function end() {
    setBusy(true);
    try {
      await endTabletSession();
    } finally {
      router.replace('/elder/pair');
    }
  }

  if (loading) {
    return (
      <main className={styles.centered} data-surface="voice">
        <p aria-live="polite">正在準備長者模式…</p>
      </main>
    );
  }
  if (!session) {
    return (
      <main className={styles.centered} data-surface="voice">
        <ShieldCheck aria-hidden="true" size={48} weight="fill" />
        <h1>長者模式已結束</h1>
        <p>請照顧員重新提供一次性平板連結。</p>
        <Link className={styles.linkButton} href="/elder/pair">
          前往平板設定
        </Link>
      </main>
    );
  }

  return (
    <main className={styles.page} data-surface="voice">
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>小暖陪伴 · 長者模式</p>
          <h1>{session.preferred_name || session.display_name}，您好</h1>
        </div>
        <button className={styles.endButton} disabled={busy} onClick={() => void end()} type="button">
          <SignOut aria-hidden="true" size={26} />
          結束使用
        </button>
      </header>

      <section aria-label="對話內容" className={styles.chat}>
        {messages.length === 0 && (
          <div className={styles.welcome}>
            <ChatCircleDots aria-hidden="true" size={48} weight="fill" />
            <h2>今天想聊些什麼？</h2>
            <p>您可以打字告訴小暖。疾病與用藥資料只會用來避免不安全的回應。</p>
          </div>
        )}
        {messages.map((message) => (
          <p className={message.role === 'elder' ? styles.elderMessage : styles.aiMessage} key={message.id}>
            <strong>{message.role === 'elder' ? '您' : '小暖'}</strong>
            <span>{message.text}</span>
          </p>
        ))}
        {busy && <p aria-live="polite">小暖正在回覆…</p>}
        {error && (
          <p className={styles.error} role="alert">
            目前無法回覆。可能尚未完成正式陪伴同意，請照顧員協助確認。
          </p>
        )}
      </section>

      <form className={styles.composer} onSubmit={(event) => void send(event)}>
        <label htmlFor="elder-message">想對小暖說的話</label>
        <div>
          <textarea
            id="elder-message"
            maxLength={4000}
            onChange={(event) => setInput(event.target.value)}
            placeholder="在這裡打字…"
            rows={3}
            value={input}
          />
          <button disabled={busy || !input.trim()} type="submit">
            <PaperPlaneTilt aria-hidden="true" size={28} weight="fill" />
            送出
          </button>
        </div>
      </form>

      <aside className={styles.safetyNote}>
        小暖提供陪伴，不會診斷、改藥、停藥或取代醫療與緊急服務。
      </aside>
    </main>
  );
}
