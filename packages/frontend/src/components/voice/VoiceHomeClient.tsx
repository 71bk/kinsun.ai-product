'use client';

import { HourglassMedium, ShieldCheck } from '@phosphor-icons/react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { CompanionTextPanel } from '@/components/companion/CompanionTextPanel';
import { ElderShell } from '@/components/elder/ElderShell';
import { InputModeToggle, type InputMode } from '@/components/InputModeToggle';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { activeBasicVoiceConsent, listConsents } from '@/lib/api/consent';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import { readDevPreviewState } from './dev-preview';
import { VoiceInteractionPanel } from './VoiceInteractionPanel';
import styles from './VoiceHomeClient.module.css';

/**
 * The elder voice companion screen. Moved out of `app/page.tsx` so the route
 * can fork server-side on session-cookie presence: signed-in visitors reach
 * this canonical voice flow; signed-out visitors get the public landing page
 * instead (see `app/page.tsx`). Core still re-authorizes every read regardless
 * of which branch rendered it.
 */
export function VoiceHomeClient() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [configLoadFailed, setConfigLoadFailed] = useState(false);
  const [isDevPreview, setIsDevPreview] = useState(false);
  const [inputMode, setInputMode] = useState<InputMode>('voice');
  const [consentGranted, setConsentGranted] = useState<boolean | null>(null);
  const [consentError, setConsentError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig()
      .then((nextConfig) => {
        if (!cancelled) setConfig(nextConfig);
      })
      .catch(() => {
        if (!cancelled) setConfigLoadFailed(true);
      });
    // The preview needs no credentials — it renders CompanionCharacter's
    // states only, opens no socket (see VoiceInteractionPanel's isPreview
    // gate), so it must not be blocked behind a real voice session existing.
    setIsDevPreview(readDevPreviewState() !== null);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (config?.credentialStatus !== 'present' || !config.elderId) return;
    let cancelled = false;
    listConsents(config, config.elderId)
      .then((items) => {
        if (!cancelled) setConsentGranted(activeBasicVoiceConsent(items) !== null);
      })
      .catch(() => {
        if (!cancelled) setConsentError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [config]);

  // The preview needs no credentials and no consent — it renders
  // CompanionCharacter's states only and opens no socket (see
  // VoiceInteractionPanel's isPreview gate), so none of the real-session
  // gates below should block it.
  if (isDevPreview) {
    return (
      <main className={styles.previewPage} data-surface="voice">
        <h1 className={styles.title}>小暖陪伴</h1>
        <VoiceInteractionPanel apiConfig={{ apiBaseUrl: '' }} elderId="" consentGranted />
      </main>
    );
  }

  if (configLoadFailed || config?.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證" />;
  }
  if (!config) {
    return (
      <main data-surface="voice" className={styles.loadingPage} aria-busy="true">
        <HourglassMedium
          size={48}
          weight="fill"
          aria-hidden="true"
          className={styles.loadingIcon}
        />
        <h1 className={styles.loadingTitle}>智慧長照 AI 陪伴系統</h1>
        <p role="status" aria-live="polite" className={styles.loadingMessage}>
          正在準備陪伴服務，請稍候…
        </p>
      </main>
    );
  }
  if (config.credentialStatus !== 'present' || !config.elderId) {
    return <NotLoggedIn reason="尚未設定本機 Demo 身分，請先完成登入設定" />;
  }

  return (
    <ElderShell>
      <main className={styles.page}>
        <header className={styles.header}>
          <span className={styles.eyebrow}>語音與文字陪伴</span>
          <h1 className={styles.title}>想和小暖聊什麼？</h1>
          <p className={styles.description}>
            只有在您按下開始後才會使用麥克風。聽不清楚時，小暖一定會先請您確認。
          </p>
        </header>

        {consentError && (
          <section className={styles.blockedCard} role="alert">
            <ShieldCheck aria-hidden="true" size={40} weight="fill" />
            <h2>目前無法確認同意狀態</h2>
            <p>系統不會開始錄音或送出文字，請稍後重新整理。</p>
          </section>
        )}
        {!consentError && consentGranted === null && (
          <p aria-live="polite" className={styles.statusMessage}>
            正在向 Core API 確認陪伴同意…
          </p>
        )}
        {!consentError && consentGranted === false && (
          <section className={styles.blockedCard}>
            <ShieldCheck aria-hidden="true" size={40} weight="fill" />
            <h2>請先決定是否開啟陪伴</h2>
            <p>在您明確同意前，小暖不會開啟麥克風或建立陪伴 Session。</p>
            <Link className={styles.consentLink} href="/consent">
              前往同意設定
            </Link>
          </section>
        )}
        {!consentError && consentGranted === true && (
          <section className={styles.workspace} aria-label="陪伴互動">
            <InputModeToggle mode={inputMode} onChange={setInputMode} />
            {inputMode === 'voice' ? (
              <VoiceInteractionPanel
                apiConfig={config}
                elderId={config.elderId}
                consentGranted={consentGranted}
              />
            ) : (
              <CompanionTextPanel apiConfig={config} elderId={config.elderId} />
            )}
          </section>
        )}

        <aside className={styles.safetyNote}>
          小暖提供陪伴與資料整理，不會診斷、改藥、停藥或代替醫療與緊急服務。
        </aside>
      </main>
    </ElderShell>
  );
}
