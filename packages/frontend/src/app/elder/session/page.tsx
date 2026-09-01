'use client';

import {
  ChatCircleDots,
  CheckCircle,
  Info,
  PaperPlaneTilt,
  Prohibit,
  ShieldCheck,
  SignOut,
} from '@phosphor-icons/react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type FormEvent, useEffect, useState } from 'react';
import {
  acknowledgeTabletFirstUse,
  endTabletSession,
  getCurrentTabletSession,
  revokeTabletFirstUseAcknowledgement,
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
  const [turnError, setTurnError] = useState(false);
  const [acknowledgementError, setAcknowledgementError] = useState(false);
  const [confirmingStop, setConfirmingStop] = useState(false);

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

  async function acknowledge() {
    if (!session || busy) return;
    setBusy(true);
    setAcknowledgementError(false);
    try {
      const firstUse = await acknowledgeTabletFirstUse();
      setSession({ ...session, first_use_acknowledgement: firstUse });
      window.scrollTo({ behavior: 'auto', left: 0, top: 0 });
    } catch {
      setAcknowledgementError(true);
    } finally {
      setBusy(false);
    }
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'elder', text }]);
    setInput('');
    setBusy(true);
    setTurnError(false);
    try {
      const turn = await runAssistedCompanionTurn(text);
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'assistant', text: turn.reply_text },
      ]);
    } catch {
      setTurnError(true);
    } finally {
      setBusy(false);
    }
  }

  async function stopCompanion() {
    if (!session || busy) return;
    setBusy(true);
    setAcknowledgementError(false);
    try {
      const firstUse = await revokeTabletFirstUseAcknowledgement();
      setSession({ ...session, first_use_acknowledgement: firstUse });
      window.scrollTo({ behavior: 'auto', left: 0, top: 0 });
      setMessages([]);
      setInput('');
      setConfirmingStop(false);
      setTurnError(false);
    } catch {
      setAcknowledgementError(true);
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

  const elderName = session.preferred_name || session.display_name;
  if (session.first_use_acknowledgement.status === 'REQUIRED') {
    return (
      <main className={styles.noticePage} data-surface="voice">
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>小暖陪伴 · 長者模式</p>
            <h1>{elderName}，開始前先說明</h1>
          </div>
        </header>

        <section aria-labelledby="first-use-title" className={styles.noticeCard}>
          <Info aria-hidden="true" className={styles.noticeIcon} size={56} weight="fill" />
          <h2 id="first-use-title">使用 AI 陪伴前，請先了解</h2>
          <ul>
            <li>小暖是 AI 陪伴，不是醫師，也不會診斷、改藥或停藥。</li>
            <li>您輸入的對話會交給 AI 處理，讓小暖回覆您。</li>
            <li>登記的疾病、用藥與注意事項目前不會送給 AI，也不會自動成為記憶。</li>
            <li>您可以隨時停止 AI 陪伴；停止後就不能再繼續對話。</li>
          </ul>
          <p className={styles.plainLanguageNote}>
            這是使用前確認，不是醫療同意書，也不表示照顧員代替您同意。
          </p>
          <p className={styles.policyVersion}>
            說明版本：{session.first_use_acknowledgement.policy_version}
          </p>
          {acknowledgementError && (
            <p className={styles.error} role="alert">
              目前無法記錄確認，尚未開始使用 AI。請稍後再試或請照顧員協助。
            </p>
          )}
          <div className={styles.noticeActions}>
            <button
              className={styles.primaryButton}
              disabled={busy}
              onClick={() => void acknowledge()}
              type="button"
            >
              <CheckCircle aria-hidden="true" size={30} weight="fill" />
              {busy ? '正在記錄…' : '了解並開始使用'}
            </button>
            <button
              className={styles.secondaryButton}
              disabled={busy}
              onClick={() => void end()}
              type="button"
            >
              <SignOut aria-hidden="true" size={28} />
              現在不要使用
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className={styles.page} data-surface="voice">
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>小暖陪伴 · 長者模式</p>
          <h1>{elderName}，您好</h1>
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
            <p>您可以打字告訴小暖。疾病與用藥資料目前不會送給 AI。</p>
          </div>
        )}
        {messages.map((message) => (
          <p className={message.role === 'elder' ? styles.elderMessage : styles.aiMessage} key={message.id}>
            <strong>{message.role === 'elder' ? '您' : '小暖'}</strong>
            <span>{message.text}</span>
          </p>
        ))}
        {busy && !confirmingStop && <p aria-live="polite">小暖正在回覆…</p>}
        {turnError && (
          <p className={styles.error} role="alert">
            目前無法回覆，這次訊息沒有完成。請稍後再試或請照顧員協助。
          </p>
        )}
      </section>

      {confirmingStop ? (
        <section aria-labelledby="stop-companion-title" className={styles.stopConfirmation}>
          <Prohibit aria-hidden="true" size={44} weight="fill" />
          <div>
            <h2 id="stop-companion-title">確定要停止 AI 陪伴嗎？</h2>
            <p>停止後會立即中止目前的對話。之後要再使用，必須重新閱讀並確認說明。</p>
          </div>
          {acknowledgementError && (
            <p className={styles.error} role="alert">
              目前無法停止，請稍後再試或請照顧員協助。
            </p>
          )}
          <div className={styles.confirmActions}>
            <button
              className={styles.secondaryButton}
              disabled={busy}
              onClick={() => {
                setAcknowledgementError(false);
                setConfirmingStop(false);
              }}
              type="button"
            >
              繼續使用
            </button>
            <button
              className={styles.destructiveButton}
              disabled={busy}
              onClick={() => void stopCompanion()}
              type="button"
            >
              <Prohibit aria-hidden="true" size={28} weight="fill" />
              {busy ? '正在停止…' : '確定停止 AI 陪伴'}
            </button>
          </div>
        </section>
      ) : (
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
      )}

      <aside className={styles.safetyNote}>
        <p>小暖提供陪伴，不會診斷、改藥、停藥或取代醫療與緊急服務。</p>
        {!confirmingStop && (
          <button
            className={styles.stopButton}
            disabled={busy}
            onClick={() => {
              setAcknowledgementError(false);
              setConfirmingStop(true);
            }}
            type="button"
          >
            <Prohibit aria-hidden="true" size={28} />
            停止 AI 陪伴
          </button>
        )}
      </aside>
    </main>
  );
}
