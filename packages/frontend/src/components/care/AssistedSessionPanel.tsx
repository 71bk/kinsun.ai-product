'use client';

import { useEffect, useState } from 'react';
import type { ApiConfig } from '@/lib/api/client';
import { issueAssistedSession, recordAssistedVerbalAcknowledgement, type IssuedAssistedSession } from '@/lib/api/assisted-elders';
import styles from './AssistedSessionPanel.module.css';

export function AssistedSessionPanel({ config, elderId, elderName }: {
  config: ApiConfig; elderId: string; elderName: string;
}) {
  const [handoff, setHandoff] = useState<IssuedAssistedSession | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [recorded, setRecorded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    if (!handoff) return;
    const check = () => setExpired(Date.now() >= Date.parse(handoff.pairing_expires_at));
    check();
    const timer = setInterval(check, 1000);
    return () => clearInterval(timer);
  }, [handoff]);
  const link = handoff && !expired ? `${window.location.origin}/elder/pair#${handoff.pairing_token}` : '';

  async function prepare() {
    setBusy(true); setError(''); setHandoff(null); setRecorded(false); setAgreed(false); setCopied(false);
    try { setHandoff(await issueAssistedSession(config, elderId)); }
    catch { setError('目前無法準備平板，請確認服務關係仍有效後重試。'); }
    finally { setBusy(false); }
  }
  async function record() {
    if (!handoff || !agreed || expired) return;
    setBusy(true); setError('');
    try {
      const result = await recordAssistedVerbalAcknowledgement(config, elderId, handoff.assisted_session_id);
      if (result.status !== 'ACKNOWLEDGED') throw new Error();
      setRecorded(true);
    } catch { setError('尚未完成使用確認，請確認連結未過期後重試。'); }
    finally { setBusy(false); }
  }
  return <section className={styles.panel} aria-labelledby="assisted-title">
    <h2 id="assisted-title">協助 {elderName} 使用陪伴</h2>
    <p>長者不需要帳號或密碼。請由照服員準備平板，再協助開啟語音。</p>
    <button disabled={busy} onClick={() => void prepare()} type="button">{handoff ? '重新準備平板' : '準備陪伴平板'}</button>
    <p className={styles.note}>重新準備會結束這位長者原本的平板使用。</p>
    {handoff && !expired && <>
      <h3>請向長者說明</h3>
      <p>「小暖是 AI，會處理您說的話並回覆，不是醫師，不會診斷或改藥，也不會自動保存長期記憶。您隨時可以說停止，或請我協助停止。現在願意和小暖聊聊嗎？」</p>
      {recorded ? <p role="status">已完成使用確認，可以交付平板。</p> : <>
        <label className={styles.check}><input checked={agreed} onChange={(event) => setAgreed(event.target.checked)} type="checkbox" />
          我已說明用途，長者本人已清楚表達願意使用；我只協助操作與記錄。</label>
        <p className={styles.note}>尚未表達意願或需要代理人授權時，請暫停交付並聯絡負責人。</p>
        <button disabled={!agreed || busy} onClick={() => void record()} type="button">記錄長者口頭確認</button>
      </>}
      <label className={styles.linkLabel}>一次性平板連結<input readOnly value={link} /></label>
      <div className={styles.actions}>
        <button type="button" disabled={!recorded || busy} onClick={() => {
          void navigator.clipboard.writeText(link).then(() => setCopied(true)).catch(() => setError('無法自動複製，請手動複製上方連結。'));
        }}>{copied ? '已複製' : '複製平板連結'}</button>
        {recorded && <a href={link}>在這台裝置開啟長者模式</a>}
      </div>
      <p className={styles.note}>在這台裝置開啟會登出照服員。連結可使用一次，請在 {new Date(handoff.pairing_expires_at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })} 前完成配對。</p>
    </>}
    {expired && <p role="status">平板連結已過期，請重新準備。</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
