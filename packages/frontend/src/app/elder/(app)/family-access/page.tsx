'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { StateBadge, type WorkflowState } from '@/components/StateCard';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { ApiRequestError } from '@/lib/api/client';
import { activeFamilySharingConsent, listConsents } from '@/lib/api/consent';
import {
  createFamilyInvitation,
  listFamilyInvitations,
  revokeFamilyInvitation,
  type CreatedFamilyInvitation,
  type FamilyInvitationStatus,
} from '@/lib/api/family-invitations';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './FamilyAccessPage.module.css';

const STATUS_LABELS: Record<FamilyInvitationStatus['status'], string> = {
  ISSUED: '等待使用',
  REDEEMED: '已使用',
  EXPIRED: '已過期',
  REVOKED: '已撤銷',
  LOCKED: '已鎖定',
};

const STATUS_STATE: Record<FamilyInvitationStatus['status'], WorkflowState> = {
  ISSUED: 'candidate',
  REDEEMED: 'confirmed',
  EXPIRED: 'withdrawn',
  REVOKED: 'withdrawn',
  LOCKED: 'needsReview',
};

export default function ElderFamilyAccessPage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [configFailed, setConfigFailed] = useState(false);
  const [email, setEmail] = useState('');
  const [familyConsent, setFamilyConsent] = useState<boolean | null>(null);
  const [invitations, setInvitations] = useState<FamilyInvitationStatus[] | null>(null);
  const [created, setCreated] = useState<CreatedFamilyInvitation | null>(null);
  const [pendingCreate, setPendingCreate] = useState(false);
  const [pendingRevoke, setPendingRevoke] = useState<FamilyInvitationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const elderId = config?.elderId ?? '';

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig()
      .then((next) => {
        if (!cancelled) setConfig(next);
      })
      .catch(() => {
        if (!cancelled) setConfigFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const reload = useCallback(async () => {
    if (!elderId) return;
    setError(null);
    setInvitations(null);
    try {
      const consents = await listConsents(apiConfig, elderId);
      const enabled = activeFamilySharingConsent(consents) !== null;
      setFamilyConsent(enabled);
      if (!enabled) {
        setInvitations([]);
        return;
      }
      setInvitations(await listFamilyInvitations(apiConfig, elderId));
    } catch {
      setError('目前無法讀取家屬分享狀態，請稍後再試。');
    }
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (config?.credentialStatus === 'present' && elderId) void reload();
  }, [config?.credentialStatus, elderId, reload]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!busy) setPendingCreate(true);
  }

  async function confirmCreate() {
    setBusy(true);
    setError(null);
    setCreated(null);
    setCopyStatus(null);
    try {
      const result = await createFamilyInvitation(apiConfig, elderId, email.trim() || undefined);
      setCreated(result);
      setEmail('');
      setPendingCreate(false);
      await reload();
    } catch (caught) {
      setPendingCreate(false);
      setError(
        caught instanceof ApiRequestError && caught.status === 409
          ? '建立邀請前，請先在同意設定中開啟「家屬報表分享」。'
          : '邀請建立失敗，請稍後再試。',
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmRevoke() {
    if (!pendingRevoke) return;
    setBusy(true);
    setError(null);
    try {
      await revokeFamilyInvitation(apiConfig, elderId, pendingRevoke.invitation_id);
      setPendingRevoke(null);
      await reload();
    } catch {
      setPendingRevoke(null);
      setError('無法撤銷這組邀請碼，可能已被使用或過期。');
    } finally {
      setBusy(false);
    }
  }

  async function copyCode() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.invitation_code);
      setCopyStatus('邀請碼已複製。');
    } catch {
      setCopyStatus('無法自動複製，請手動記下邀請碼。');
    }
  }

  if (configFailed || config?.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證。" />;
  }
  if (!config) {
    return (
      <main className={styles.bootstrap} data-surface="voice" role="status">
        正在確認登入狀態…
      </main>
    );
  }
  if (config.credentialStatus !== 'present' || !elderId) {
    return <NotLoggedIn reason="請先以長者身分登入，再建立家屬邀請碼。" />;
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <span className={styles.eyebrow}>只分享正式報表</span>
        <h1>家屬分享</h1>
        <p>一次性邀請碼只建立家屬關係，不會讓家屬看到逐字稿、記憶、草稿或照護內部資料。</p>
      </header>

      {error && (
        <p className={styles.error} role="alert">
          {error} <Link href="/elder/consent">前往同意設定</Link>
        </p>
      )}

      {familyConsent === null && !error && (
        <p aria-live="polite" className={styles.loading}>
          正在確認家屬分享同意…
        </p>
      )}

      {familyConsent === false && !error && (
        <section className={styles.consentRequired}>
          <h2>家屬分享尚未開啟</h2>
          <p>您必須先明確開啟 FAMILY_SHARING 同意，Core 才會建立邀請碼。</p>
          <Link href="/elder/consent">前往同意設定</Link>
        </section>
      )}

      {familyConsent && (
        <>
          <form className={styles.form} onSubmit={submit}>
            <label htmlFor="invitee-email">家屬 Email（建議填寫）</label>
            <p id="invitee-email-hint">填寫後，只有該 Google 帳號能使用邀請碼。</p>
            <input
              aria-describedby="invitee-email-hint"
              autoComplete="email"
              id="invitee-email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="family@example.com"
              type="email"
              value={email}
            />
            <button disabled={busy} type="submit">
              產生一次性邀請碼
            </button>
          </form>

          {created && (
            <section aria-live="polite" className={styles.created}>
              <h2>請現在把這組邀請碼交給家屬</h2>
              <p className={styles.code}>{created.invitation_code}</p>
              <p>邀請碼 24 小時後失效；關閉畫面後，系統不會再顯示完整內容。</p>
              <button onClick={() => void copyCode()} type="button">
                複製邀請碼
              </button>
              {copyStatus && <p>{copyStatus}</p>}
            </section>
          )}

          <section aria-labelledby="invitation-list-title" className={styles.records}>
            <h2 id="invitation-list-title">邀請紀錄</h2>
            {!invitations ? (
              <p className={styles.loading}>正在讀取邀請紀錄…</p>
            ) : invitations.length === 0 ? (
              <EmptyState description="目前沒有邀請紀錄。" title="尚未建立邀請" />
            ) : (
              <ul>
                {invitations.map((item) => (
                  <li key={item.invitation_id}>
                    <StateBadge
                      label={STATUS_LABELS[item.status]}
                      state={STATUS_STATE[item.status]}
                    />
                    <span>到期：{new Date(item.expires_at).toLocaleString('zh-TW')}</span>
                    <span>分享範圍：{item.share_scope.length} 種正式報表</span>
                    {item.status === 'ISSUED' && (
                      <button disabled={busy} onClick={() => setPendingRevoke(item)} type="button">
                        撤銷邀請
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <ConfirmationDialog
        busy={busy}
        confirmLabel="建立邀請碼"
        description="Core 會再次確認 FAMILY_SHARING 同意，並建立只能使用一次、24 小時失效的邀請碼。"
        onCancel={() => setPendingCreate(false)}
        onConfirm={() => void confirmCreate()}
        open={pendingCreate}
        title="確認建立家屬邀請？"
      />
      <ConfirmationDialog
        busy={busy}
        confirmLabel="撤銷邀請"
        description="撤銷後，這組尚未使用的邀請碼將不能再兌換。"
        onCancel={() => setPendingRevoke(null)}
        onConfirm={() => void confirmRevoke()}
        open={pendingRevoke !== null}
        title="確認撤銷這組邀請？"
        tone="destructive"
      />
    </main>
  );
}
