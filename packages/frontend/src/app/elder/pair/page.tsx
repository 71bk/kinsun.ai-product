'use client';

import { ArrowRight, DeviceTablet, ShieldCheck } from '@phosphor-icons/react';
import { useRouter } from 'next/navigation';
import { type FormEvent, useEffect, useState } from 'react';
import { exchangeTabletPairing } from '@/lib/api/assisted-elders';
import styles from './TabletPairPage.module.css';

const TOKEN_PATTERN = /^ep1_[A-Za-z0-9_-]{43}$/;

function tokenFrom(value: string): string {
  const trimmed = value.trim();
  const fragment = trimmed.includes('#') ? trimmed.slice(trimmed.lastIndexOf('#') + 1) : trimmed;
  return TOKEN_PATTERN.test(fragment) ? fragment : '';
}

export default function TabletPairPage() {
  const router = useRouter();
  const [pairingInput, setPairingInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const token = tokenFrom(window.location.hash.replace(/^#/, ''));
    if (!token) return;
    setPairingInput(token);
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  }, []);

  async function activate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = tokenFrom(pairingInput);
    if (!token) {
      setError(true);
      return;
    }
    setBusy(true);
    setError(false);
    try {
      await exchangeTabletPairing(token);
      setPairingInput('');
      router.replace('/elder/session');
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page} data-surface="voice">
      <section className={styles.card}>
        <span className={styles.icon}>
          <DeviceTablet aria-hidden="true" size={46} weight="fill" />
        </span>
        <p className={styles.eyebrow}>長者平板設定</p>
        <h1>開啟小暖陪伴</h1>
        <p>請貼上照顧員提供的一次性平板連結。啟用後，這台平板不會保留照顧員帳號。</p>
        <form className={styles.form} onSubmit={(event) => void activate(event)}>
          <label htmlFor="pairing-link">一次性平板連結</label>
          <textarea
            autoComplete="off"
            id="pairing-link"
            onChange={(event) => setPairingInput(event.target.value)}
            placeholder="貼上連結"
            required
            rows={3}
            spellCheck={false}
            value={pairingInput}
          />
          {error && (
            <p className={styles.error} role="alert">
              連結無效、已使用或已過期，請照顧員重新產生。
            </p>
          )}
          <button disabled={busy} type="submit">
            {busy ? '正在安全啟用…' : '進入長者模式'}
            {!busy && <ArrowRight aria-hidden="true" size={28} />}
          </button>
        </form>
        <p className={styles.securityNote}>
          <ShieldCheck aria-hidden="true" size={26} weight="fill" />
          連結只能使用一次，長者模式也會自動逾時。
        </p>
      </section>
    </main>
  );
}
