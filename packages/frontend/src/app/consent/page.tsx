'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ConsentSummary } from '@/components/consent/ConsentSummary';
import { LongTermMemoryConsentPanel } from '@/components/consent/LongTermMemoryConsentPanel';
import { ElderShell } from '@/components/elder/ElderShell';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { FamilySharingConsentPanel } from '@/components/FamilySharingConsentPanel';
import { ConsentPanel } from '@/components/voice/ConsentPanel';
import {
  activeBasicVoiceConsent,
  activeFamilySharingConsent,
  activeLongTermMemoryConsent,
  listConsents,
  type ConsentRecord,
} from '@/lib/api/consent';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './ConsentPage.module.css';

export default function ConsentPage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [configFailed, setConfigFailed] = useState(false);
  const [consent, setConsent] = useState<ConsentRecord | null | undefined>(undefined);
  const [memoryConsent, setMemoryConsent] = useState<ConsentRecord | null | undefined>(undefined);
  const [familyConsent, setFamilyConsent] = useState<ConsentRecord | null | undefined>(undefined);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig()
      .then((nextConfig) => {
        if (!cancelled) setConfig(nextConfig);
      })
      .catch(() => {
        if (!cancelled) setConfigFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (config?.credentialStatus !== 'present' || !config.elderId) return;
    let cancelled = false;
    listConsents(config, config.elderId)
      .then((items) => {
        if (!cancelled) {
          setConsent(activeBasicVoiceConsent(items));
          setMemoryConsent(activeLongTermMemoryConsent(items));
          setFamilyConsent(activeFamilySharingConsent(items));
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [config]);

  if (configFailed || config?.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證" />;
  }
  if (!config) {
    return (
      <main className={styles.loading} data-surface="voice" role="status">
        正在確認登入狀態…
      </main>
    );
  }
  if (config.credentialStatus !== 'present' || !config.elderId) {
    return <NotLoggedIn reason="尚未設定本機 Demo 身分，請先完成登入設定" />;
  }
  if (loadError) {
    return <NotLoggedIn reason="無法向 Core API 讀取同意狀態；系統已停止，不會推測結果" />;
  }
  if (consent === undefined || memoryConsent === undefined || familyConsent === undefined)
    return (
      <ElderShell>
        <main aria-live="polite" className={styles.loading}>
          正在向 Core API 查詢同意狀態…
        </main>
      </ElderShell>
    );

  return (
    <ElderShell>
      <main className={styles.page}>
        <header className={styles.header}>
          <span className={styles.eyebrow}>用途分開決定</span>
          <h1>同意設定</h1>
          <p>每一項用途都能分別開啟或撤回。這裡只列出目前有正式功能與 Core workflow 支援的選項。</p>
        </header>

        <ConsentSummary family={familyConsent} memory={memoryConsent} voice={consent} />

        <section aria-label="同意用途" className={styles.controls}>
          <ConsentPanel
            apiConfig={config}
            elderId={config.elderId}
            initialConsent={consent}
            onChange={setConsent}
            policyVersion={config.consentPolicyVersion}
          />
          <LongTermMemoryConsentPanel
            apiConfig={config}
            elderId={config.elderId}
            initialConsent={memoryConsent}
            onChange={setMemoryConsent}
            policyVersion={config.consentPolicyVersion}
          />
          <FamilySharingConsentPanel
            apiConfig={config}
            elderId={config.elderId}
            initialConsent={familyConsent}
            onChange={setFamilyConsent}
            policyVersion={config.consentPolicyVersion}
          />
        </section>

        <aside className={styles.boundaryNote}>
          此頁不提供健康風險分數、情緒告警、主動陪伴時段或緊急救護設定；這些功能目前沒有完整產品與
          API workflow。
        </aside>

        <nav aria-label="同意設定相關連結" className={styles.actions}>
          <Link href="/">返回陪伴首頁</Link>
          <Link href="/elder/memories">查看我的記憶</Link>
          <Link href="/elder/family-access">管理家屬邀請</Link>
        </nav>
      </main>
    </ElderShell>
  );
}
