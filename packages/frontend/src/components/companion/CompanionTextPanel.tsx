'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import { createTextSession, runCompanionTurn, type CompanionTurn } from '@/lib/api/companion';
import { CompanionCharacter } from '@/components/voice/CompanionCharacter';
import { deleteMemoryAsElder } from '@/lib/api/memories';
import { CompanionReplyAudio } from './CompanionReplyAudio';
import styles from './CompanionTextPanel.module.css';

interface CompanionTextPanelProps {
  apiConfig: ApiConfig;
  elderId: string;
}

function safeErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 404) return '目前無法開始陪伴，請確認身分與長者授權範圍。';
    if (error.status === 409) return '這一輪已結束，請重新送出建立新的一輪。';
    if (error.status === 503)
      return '陪伴服務暫時沒有回應，請稍後再試。您可以到「我的記憶」確認保存狀態。';
  }
  return '目前無法確認這次操作結果，請稍後再試，或到「我的記憶」查看。';
}

export function CompanionTextPanel({ apiConfig, elderId }: CompanionTextPanelProps) {
  const [inputText, setInputText] = useState('');
  const [submittedText, setSubmittedText] = useState('');
  const [turn, setTurn] = useState<CompanionTurn | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);
  const command = useRef(false);
  const receiptRegion = useRef<HTMLDivElement>(null);
  const [undoBusy, setUndoBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (turn?.memory_updates?.length) {
      receiptRegion.current?.scrollIntoView?.({ block: 'center', behavior: 'instant' });
    }
  }, [turn]);
  useEffect(() => {
    setTurn(null);
    setSubmittedText('');
    setInputText('');
    setError(null);
    setNotice(null);
    setBusy(false);
    setUndoBusy(false);
    command.current = false;
    return () => {
      request.current += 1;
    };
  }, [elderId, apiConfig]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const currentText = inputText.trim();
    if (!currentText || command.current) return;
    command.current = true;
    const currentRequest = ++request.current;

    setBusy(true);
    setError(null);
    setTurn(null);
    setNotice(null);
    try {
      const session = await createTextSession(apiConfig, elderId);
      const result = await runCompanionTurn(apiConfig, session.session_id, currentText);
      if (currentRequest !== request.current) return;
      setSubmittedText(currentText);
      setTurn(result);
      setInputText('');
    } catch (err) {
      if (currentRequest === request.current) setError(safeErrorMessage(err));
    } finally {
      if (currentRequest === request.current) {
        command.current = false;
        setBusy(false);
      }
    }
  }

  async function undoMemory(memory: NonNullable<CompanionTurn['memory_updates']>[number]) {
    if (command.current) return;
    command.current = true;
    const currentRequest = request.current;
    setUndoBusy(true);
    setError(null);
    try {
      await deleteMemoryAsElder(apiConfig, elderId, {
        memoryId: memory.memory_id,
        version: memory.version,
      });
      if (currentRequest !== request.current) return;
      setTurn((current) => (current ? { ...current, memory_updates: [] } : current));
      setNotice('已撤銷這筆記憶，新對話不會再使用它。');
    } catch (err) {
      if (currentRequest !== request.current) return;
      if (err instanceof ApiRequestError && [401, 403, 404].includes(err.status)) {
        setTurn(null);
        setSubmittedText('');
      }
      setError(safeErrorMessage(err));
    } finally {
      if (currentRequest === request.current) {
        command.current = false;
        setUndoBusy(false);
      }
    }
  }

  const message = busy
    ? '我正在整理回答，請稍等一下。'
    : (turn?.reply_text ?? '你好啊！今天想聊什麼呢？');

  return (
    <section aria-labelledby="companion-title" className={styles.panel}>
      <div className={styles.modeNotice}>
        <span>目前是文字陪伴，不會開啟麥克風</span>
      </div>

      <CompanionCharacter
        state={busy ? 'processing' : turn ? 'speaking' : 'idle'}
        message={message}
      />

      {turn && (
        <CompanionReplyAudio key={`${elderId}:${turn.agent_run_id}`} turn={turn} />
      )}

      <form className={styles.form} onSubmit={handleSubmit}>
        <label className={styles.label} id="companion-title" htmlFor="companion-input">
          想和小暖說什麼？
        </label>
        <textarea
          id="companion-input"
          value={inputText}
          onChange={(event) => setInputText(event.target.value)}
          maxLength={4000}
          rows={4}
          disabled={busy}
          placeholder="例如：我今天早餐吃了粥。"
          className={styles.textarea}
        />
        <button
          type="submit"
          disabled={busy || inputText.trim().length === 0}
          className={styles.submit}
        >
          {busy ? '正在安全處理…' : '送出文字'}
        </button>
        <small className={styles.hint}>
          開啟長期記憶後，支援的本人偏好可自動保存並撤銷；照護事件另依用途同意與人工覆核處理，不保存完整逐字稿。
        </small>
      </form>

      <div aria-live="polite" className={styles.result} ref={receiptRegion}>
        {submittedText && turn && <p className={styles.hint}>您剛才輸入：「{submittedText}」</p>}
        {turn?.memory_updates?.map((memory) => (
          <div className={styles.form} key={`${memory.memory_id}:${memory.version}`}>
            <p>
              <strong>已記住</strong>：{memory.content}
            </p>
            <p className={styles.hint}>
              來源：您本人的自述，供日後聊天使用。同類偏好以最新陳述更新。
            </p>
            <button
              type="button"
              className={styles.submit}
              disabled={busy || undoBusy}
              onClick={() => void undoMemory(memory)}
            >
              {undoBusy ? '撤銷中…' : '撤銷這筆記憶'}
            </button>
          </div>
        ))}
        {notice && <p role="status">{notice}</p>}
        {turn && turn.safety_decision !== 'ALLOW' && (
          <p className={styles.safetyMessage}>系統已套用安全回覆，沒有把高風險內容當成醫療建議。</p>
        )}
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
      </div>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.submit}
          disabled={busy || undoBusy}
          onClick={() => {
            request.current += 1;
            setTurn(null);
            setSubmittedText('');
            setInputText('');
            setError(null);
            setNotice(null);
          }}
        >
          開始新對話
        </button>
        <Link href="/elder/memories">我的記憶</Link>
        <Link href="/elder/consent">記憶與同意設定</Link>
      </div>
    </section>
  );
}
