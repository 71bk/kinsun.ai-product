'use client';

import { ArrowRight, CheckCircle, SealCheck } from '@phosphor-icons/react';
import Link from 'next/link';
import { type FormEvent, useEffect, useRef, useState } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './JoinPage.module.css';

const TOKEN_PATTERN = /^wi1_[A-Za-z0-9_-]{43}$/;
const MIN_PASSWORD_LENGTH = 12;

/** Accepts a bare credential or a full link; the credential is the fragment. */
function tokenFrom(value: string): string {
  const trimmed = value.trim();
  const fragment = trimmed.includes('#') ? trimmed.slice(trimmed.lastIndexOf('#') + 1) : trimmed;
  return TOKEN_PATTERN.test(fragment) ? fragment : '';
}

type Problem = 'token' | 'mismatch' | 'short' | 'rejected' | 'network';

export default function JoinPage() {
  const { t } = useLocale();
  const [token, setToken] = useState('');
  const [tokenFromLink, setTokenFromLink] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [done, setDone] = useState(false);
  const doneRef = useRef<HTMLElement>(null);

  // The credential must not survive in browser history, the back stack or a
  // shared screenshot of the address bar (ADR 0024).
  useEffect(() => {
    const found = tokenFrom(window.location.hash.replace(/^#/, ''));
    if (!found) return;
    setToken(found);
    setTokenFromLink(true);
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  }, []);

  useEffect(() => {
    if (done) doneRef.current?.focus({ preventScroll: true });
  }, [done]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const credential = tokenFrom(token);
    if (!credential) {
      setProblem('token');
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      setProblem('short');
      return;
    }
    if (password !== confirmation) {
      setProblem('mismatch');
      return;
    }

    setBusy(true);
    setProblem(null);
    try {
      const response = await fetch('/backend/staff-invitations/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
          invitation_token: credential,
        }),
      });
      if (!response.ok) {
        setProblem('rejected');
        return;
      }
      // Nothing about the credential or the password outlives the request.
      setToken('');
      setPassword('');
      setConfirmation('');
      setDone(true);
    } catch {
      setProblem('network');
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <main className={styles.page}>
        <section className={styles.done} ref={doneRef} tabIndex={-1}>
          <span className={styles.doneIcon}>
            <SealCheck aria-hidden="true" size={40} weight="fill" />
          </span>
          <h1>{t('staffJoin.doneTitle')}</h1>
          <p>{t('staffJoin.doneBody')}</p>
          <Link className={styles.doneLink} href="/staff/sign-in">
            {t('staffJoin.signIn')}
            <ArrowRight aria-hidden="true" size={20} weight="bold" />
          </Link>
        </section>
      </main>
    );
  }

  const problemMessage =
    problem === 'token'
      ? t('staffJoin.tokenInvalid')
      : problem === 'short'
        ? t('staffJoin.tooShort')
        : problem === 'mismatch'
          ? t('staffJoin.mismatch')
          : problem === 'network'
            ? t('staffJoin.network')
            : problem === 'rejected'
              ? t('staffJoin.failed')
              : '';

  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <h1 className={styles.title}>{t('staffJoin.title')}</h1>
        <p className={styles.subtitle}>{t('staffJoin.subtitle')}</p>

        <form className={styles.form} onSubmit={(event) => void submit(event)}>
          {tokenFromLink && !pasteOpen ? (
            <p className={styles.tokenOk}>
              <CheckCircle aria-hidden="true" size={20} weight="fill" />
              <span>{t('staffJoin.tokenReady')}</span>
              <button
                className={styles.tokenSwap}
                onClick={() => {
                  setPasteOpen(true);
                  setTokenFromLink(false);
                  setToken('');
                }}
                type="button"
              >
                {t('staffJoin.tokenReplace')}
              </button>
            </p>
          ) : (
            <label className={styles.field}>
              <span>{t('staffJoin.token')}</span>
              <textarea
                autoComplete="off"
                onChange={(event) => setToken(event.target.value)}
                required
                rows={2}
                spellCheck={false}
                value={token}
              />
              <small>{t('staffJoin.tokenHint')}</small>
            </label>
          )}

          <label className={styles.field}>
            <span>{t('staffJoin.email')}</span>
            <input
              autoComplete="username"
              inputMode="email"
              maxLength={254}
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
            <small>{t('staffJoin.emailHint')}</small>
          </label>

          <label className={styles.field}>
            <span>{t('staffJoin.password')}</span>
            <input
              autoComplete="new-password"
              maxLength={128}
              minLength={MIN_PASSWORD_LENGTH}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
            <small>{t('staffJoin.passwordHint')}</small>
          </label>

          <label className={styles.field}>
            <span>{t('staffJoin.confirm')}</span>
            <input
              autoComplete="new-password"
              maxLength={128}
              onChange={(event) => setConfirmation(event.target.value)}
              required
              type="password"
              value={confirmation}
            />
          </label>

          {problemMessage && (
            <p className={styles.problem} role="alert">
              {problemMessage}
            </p>
          )}

          <button className={styles.submit} disabled={busy} type="submit">
            {busy ? t('staffJoin.submitting') : t('staffJoin.submit')}
          </button>
        </form>
      </section>
    </main>
  );
}
