'use client';

import {
  ArrowClockwise,
  ArrowLeft,
  Check,
  CheckCircle,
  Clock,
  Copy,
  EnvelopeSimple,
  Info,
  LockKey,
  SpinnerGap,
  Ticket,
  Trash,
  UserCheck,
  UsersThree,
  WarningCircle,
  XCircle,
} from '@phosphor-icons/react';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { ApiRequestError } from '@/lib/api/client';
import {
  createFamilyInvitation,
  listFamilyInvitations,
  revokeFamilyInvitation,
  type CreatedFamilyInvitation,
  type FamilyInvitationStatus,
  type FamilyShareScope,
} from '@/lib/api/family-invitations';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

const STATUS_LABELS: Record<FamilyInvitationStatus['status'], string> = {
  ISSUED: '等待使用',
  REDEEMED: '已使用',
  EXPIRED: '已過期',
  REVOKED: '已撤銷',
  LOCKED: '已鎖定',
};

const SCOPE_LABELS: Record<FamilyShareScope, string> = {
  REPORT_DAILY: '每日摘要',
  REPORT_WEEKLY: '每週摘要',
  REPORT_MONTHLY: '每月摘要',
  REPORT_IMPORTANT_EVENT: '重要事件',
};

const cardStyle: CSSProperties = {
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-1)',
  padding: 'var(--card-pad)',
};

const primaryButtonStyle: CSSProperties = {
  alignItems: 'center',
  background: 'var(--color-primary)',
  border: 0,
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-on-primary)',
  cursor: 'pointer',
  display: 'inline-flex',
  fontSize: 'var(--text-base)',
  fontWeight: 700,
  gap: 'var(--space-2)',
  justifyContent: 'center',
  minHeight: 'var(--touch-rec)',
  padding: 'var(--space-3) var(--space-5)',
  textDecoration: 'none',
};

const secondaryButtonStyle: CSSProperties = {
  ...primaryButtonStyle,
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border-strong)',
  color: 'var(--color-primary-text)',
};

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '時間未提供';
  return new Intl.DateTimeFormat('zh-TW', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function InvitationStatusBadge({ status }: { status: FamilyInvitationStatus['status'] }) {
  let Icon = Clock;
  let foreground = 'var(--state-review-fg)';
  let background = 'var(--state-review-bg)';

  if (status === 'REDEEMED') {
    Icon = UserCheck;
    foreground = 'var(--state-confirmed-fg)';
    background = 'var(--state-confirmed-bg)';
  } else if (status === 'EXPIRED') {
    Icon = Clock;
    foreground = 'var(--state-candidate-fg)';
    background = 'var(--state-candidate-bg)';
  } else if (status === 'REVOKED') {
    Icon = XCircle;
    foreground = 'var(--state-withdrawn-fg)';
    background = 'var(--state-withdrawn-bg)';
  } else if (status === 'LOCKED') {
    Icon = LockKey;
    foreground = 'var(--state-withdrawn-fg)';
    background = 'var(--state-withdrawn-bg)';
  }

  return (
    <span
      style={{
        alignItems: 'center',
        background,
        borderRadius: 'var(--radius-full)',
        color: foreground,
        display: 'inline-flex',
        fontSize: 'var(--text-sm)',
        fontWeight: 700,
        gap: 'var(--space-1)',
        padding: 'var(--space-1) var(--space-3)',
      }}
    >
      <Icon aria-hidden="true" size={20} weight="fill" />
      {STATUS_LABELS[status]}
    </span>
  );
}

export default function ElderFamilyAccessPage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [email, setEmail] = useState('');
  const [invitations, setInvitations] = useState<FamilyInvitationStatus[]>([]);
  const [created, setCreated] = useState<CreatedFamilyInvitation | null>(null);
  const [creating, setCreating] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  const [listError, setListError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ message: string; showConsentLink: boolean } | null>(
    null,
  );
  const [notice, setNotice] = useState<string | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const elderId = config?.elderId ?? '';

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((next) => {
      if (!cancelled) setConfig(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const reload = useCallback(async () => {
    if (!elderId) return;
    setListLoading(true);
    setListError(null);
    try {
      setInvitations(await listFamilyInvitations(apiConfig, elderId));
    } catch {
      setListError('目前無法讀取邀請紀錄，請稍後再試。');
    } finally {
      setListLoading(false);
    }
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (config?.credentialStatus === 'present' && elderId) void reload();
  }, [config?.credentialStatus, elderId, reload]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setActionError(null);
    setNotice(null);
    setCreated(null);
    setCopyStatus('idle');
    try {
      const result = await createFamilyInvitation(apiConfig, elderId, email.trim() || undefined);
      setCreated(result);
      setEmail('');
      await reload();
    } catch (caught) {
      setActionError(
        caught instanceof ApiRequestError && caught.status === 409
          ? {
              message: '建立邀請前，請先在同意設定中開啟「家庭分享」。',
              showConsentLink: true,
            }
          : { message: '邀請建立失敗，請稍後再試。', showConsentLink: false },
      );
    } finally {
      setCreating(false);
    }
  }

  async function copyInvitationCode() {
    if (!created) return;
    try {
      if (!navigator.clipboard) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(created.invitation_code);
      setCopyStatus('copied');
    } catch {
      setCopyStatus('failed');
    }
  }

  async function revoke(invitationId: string) {
    setRevokingId(invitationId);
    setActionError(null);
    setNotice(null);
    try {
      await revokeFamilyInvitation(apiConfig, elderId, invitationId);
      setConfirmRevokeId(null);
      setNotice('邀請已撤銷，原邀請碼無法再使用。');
      await reload();
    } catch {
      setActionError({
        message: '無法撤銷這組邀請碼，可能已被使用或過期。請重新整理後再試。',
        showConsentLink: false,
      });
    } finally {
      setRevokingId(null);
    }
  }

  if (!config) {
    return (
      <main
        aria-busy="true"
        data-surface="family"
        style={{ color: 'var(--color-foreground)', margin: '0 auto', maxWidth: 760, padding: 24 }}
      >
        <section aria-live="polite" style={cardStyle}>
          <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
            <SpinnerGap aria-hidden="true" className="spin" size={30} />
            正在確認登入與家屬分享設定…
          </div>
        </section>
      </main>
    );
  }

  if (config.credentialStatus !== 'present' || !elderId) {
    return <NotLoggedIn reason="請先以長者身分登入，再建立家屬邀請碼。" />;
  }

  return (
    <main
      data-surface="family"
      style={{
        color: 'var(--color-foreground)',
        margin: '0 auto',
        maxWidth: 760,
        padding: 'var(--space-6)',
      }}
    >
      <header style={{ marginBottom: 'var(--space-8)' }}>
        <div
          style={{
            alignItems: 'center',
            color: 'var(--color-primary-text)',
            display: 'flex',
            fontSize: 'var(--text-sm)',
            fontWeight: 700,
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-2)',
          }}
        >
          <UsersThree aria-hidden="true" size={26} weight="fill" />
          家人共同關心
        </div>
        <h1 style={{ fontSize: 'var(--text-2xl)', lineHeight: 1.25, margin: 0 }}>家屬分享</h1>
        <p
          style={{
            color: 'var(--color-muted-foreground)',
            fontSize: 'var(--text-base)',
            lineHeight: 'var(--leading-body)',
            marginBottom: 0,
          }}
        >
          建立一次性邀請碼，讓你信任的家屬查看同意分享的照護摘要。你可以隨時撤銷尚未使用的邀請。
        </p>
      </header>

      <div style={{ display: 'grid', gap: 'var(--space-6)' }}>
        <section aria-labelledby="create-invitation-title" style={cardStyle}>
          <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
            <Ticket aria-hidden="true" color="var(--color-primary-text)" size={34} />
            <div>
              <div
                style={{
                  color: 'var(--color-primary-text)',
                  fontSize: 'var(--text-sm)',
                  fontWeight: 700,
                }}
              >
                步驟一
              </div>
              <h2 id="create-invitation-title" style={{ fontSize: 'var(--text-xl)', margin: 0 }}>
                建立家屬邀請
              </h2>
            </div>
          </div>

          <div
            style={{
              alignItems: 'flex-start',
              background: 'var(--state-review-bg)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              gap: 'var(--space-2)',
              margin: 'var(--space-5) 0',
              padding: 'var(--space-3)',
            }}
          >
            <Info aria-hidden="true" color="var(--state-review-fg)" size={24} weight="fill" />
            <small style={{ fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-body)' }}>
              邀請碼只能使用一次，並會在 24 小時後失效。填寫 Email 可限制只有指定的 Google 帳號使用。
            </small>
          </div>

          <form onSubmit={submit}>
            <label htmlFor="invitee-email" style={{ display: 'block', fontWeight: 700 }}>
              家屬 Email
              <span
                style={{
                  color: 'var(--color-muted-foreground)',
                  fontSize: 'var(--text-sm)',
                  fontWeight: 400,
                  marginLeft: 'var(--space-2)',
                }}
              >
                選填，但建議填寫
              </span>
            </label>
            <div style={{ position: 'relative' }}>
              <EnvelopeSimple
                aria-hidden="true"
                color="var(--color-muted-foreground)"
                size={24}
                style={{ left: 14, position: 'absolute', top: 22 }}
              />
              <input
                aria-describedby="invitee-email-help"
                autoComplete="email"
                disabled={creating}
                id="invitee-email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="family@example.com"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border-strong)',
                  borderRadius: 'var(--radius-md)',
                  boxSizing: 'border-box',
                  color: 'var(--color-foreground)',
                  fontSize: 'var(--text-base)',
                  marginTop: 'var(--space-2)',
                  minHeight: 'var(--touch-rec)',
                  padding: 'var(--space-3) var(--space-3) var(--space-3) var(--space-12)',
                  width: '100%',
                }}
                type="email"
                value={email}
              />
            </div>
            <p
              id="invitee-email-help"
              style={{ color: 'var(--color-muted-foreground)', fontSize: 'var(--text-sm)' }}
            >
              未填寫時，任何拿到邀請碼且完成登入的人都能使用。
            </p>
            <button
              disabled={creating}
              style={{ ...primaryButtonStyle, opacity: creating ? 0.7 : 1 }}
              type="submit"
            >
              {creating ? (
                <SpinnerGap aria-hidden="true" className="spin" size={24} />
              ) : (
                <Ticket aria-hidden="true" size={24} />
              )}
              {creating ? '正在建立…' : '產生一次性邀請碼'}
            </button>
          </form>
        </section>

        {created && (
          <section
            aria-labelledby="created-invitation-title"
            aria-live="polite"
            style={{
              ...cardStyle,
              background: 'var(--state-confirmed-bg)',
              borderColor: 'var(--state-confirmed-fg)',
            }}
          >
            <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
              <CheckCircle
                aria-hidden="true"
                color="var(--state-confirmed-fg)"
                size={36}
                weight="fill"
              />
              <div>
                <div
                  style={{
                    color: 'var(--state-confirmed-fg)',
                    fontSize: 'var(--text-sm)',
                    fontWeight: 700,
                  }}
                >
                  邀請建立成功
                </div>
                <h2 id="created-invitation-title" style={{ fontSize: 'var(--text-xl)', margin: 0 }}>
                  請現在把邀請碼交給家屬
                </h2>
              </div>
            </div>

            <div
              aria-label={`邀請碼 ${created.invitation_code}`}
              style={{
                background: 'var(--color-surface)',
                border: '2px dashed var(--state-confirmed-fg)',
                borderRadius: 'var(--radius-md)',
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                fontSize: 'var(--text-2xl)',
                fontWeight: 800,
                letterSpacing: 3,
                margin: 'var(--space-5) 0 var(--space-3)',
                overflowWrap: 'anywhere',
                padding: 'var(--space-5)',
                textAlign: 'center',
              }}
            >
              {created.invitation_code}
            </div>
            <p style={{ color: 'var(--color-muted-foreground)', fontSize: 'var(--text-sm)' }}>
              到期時間：{formatDate(created.expires_at)}。離開此畫面後，系統不會再顯示完整邀請碼。
            </p>
            <button onClick={() => void copyInvitationCode()} style={primaryButtonStyle} type="button">
              {copyStatus === 'copied' ? (
                <Check aria-hidden="true" size={24} weight="bold" />
              ) : (
                <Copy aria-hidden="true" size={24} />
              )}
              {copyStatus === 'copied' ? '已複製邀請碼' : '複製邀請碼'}
            </button>
            {copyStatus === 'copied' && (
              <p aria-live="polite" style={{ color: 'var(--state-confirmed-fg)', marginBottom: 0 }}>
                已複製，可以貼到訊息中傳給家屬。
              </p>
            )}
            {copyStatus === 'failed' && (
              <p aria-live="assertive" role="alert" style={{ color: 'var(--state-withdrawn-fg)' }}>
                瀏覽器無法自動複製，請長按或選取上方邀請碼手動複製。
              </p>
            )}
          </section>
        )}

        {notice && (
          <section
            aria-live="polite"
            style={{
              ...cardStyle,
              alignItems: 'center',
              background: 'var(--state-confirmed-bg)',
              borderColor: 'var(--state-confirmed-fg)',
              display: 'flex',
              gap: 'var(--space-3)',
            }}
          >
            <CheckCircle
              aria-hidden="true"
              color="var(--state-confirmed-fg)"
              size={30}
              weight="fill"
            />
            <p style={{ margin: 0 }}>{notice}</p>
          </section>
        )}

        {actionError && (
          <section
            aria-live="assertive"
            role="alert"
            style={{
              ...cardStyle,
              background: 'var(--state-withdrawn-bg)',
              borderColor: 'var(--state-withdrawn-fg)',
            }}
          >
            <div style={{ alignItems: 'flex-start', display: 'flex', gap: 'var(--space-3)' }}>
              <WarningCircle
                aria-hidden="true"
                color="var(--state-withdrawn-fg)"
                size={30}
                weight="fill"
              />
              <div>
                <strong>操作沒有完成</strong>
                <p style={{ lineHeight: 'var(--leading-body)', margin: 'var(--space-1) 0 0' }}>
                  {actionError.message}{' '}
                  {actionError.showConsentLink && <Link href="/consent">前往同意設定</Link>}
                </p>
              </div>
            </div>
          </section>
        )}

        <section aria-labelledby="invitation-history-title" style={cardStyle}>
          <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
            <UsersThree aria-hidden="true" color="var(--color-primary-text)" size={34} />
            <div>
              <div
                style={{
                  color: 'var(--color-primary-text)',
                  fontSize: 'var(--text-sm)',
                  fontWeight: 700,
                }}
              >
                步驟二
              </div>
              <h2 id="invitation-history-title" style={{ fontSize: 'var(--text-xl)', margin: 0 }}>
                邀請紀錄
              </h2>
            </div>
          </div>

          {listLoading && (
            <div
              aria-busy="true"
              aria-live="polite"
              style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)', padding: 'var(--space-6) 0' }}
            >
              <SpinnerGap aria-hidden="true" className="spin" size={28} />
              正在讀取邀請紀錄…
            </div>
          )}

          {listError && !listLoading && (
            <div
              role="alert"
              style={{
                background: 'var(--state-withdrawn-bg)',
                borderRadius: 'var(--radius-md)',
                marginTop: 'var(--space-5)',
                padding: 'var(--space-4)',
              }}
            >
              <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-2)' }}>
                <XCircle aria-hidden="true" color="var(--state-withdrawn-fg)" size={26} weight="fill" />
                <span>{listError}</span>
              </div>
              <button
                onClick={() => void reload()}
                style={{ ...secondaryButtonStyle, marginTop: 'var(--space-3)' }}
                type="button"
              >
                <ArrowClockwise aria-hidden="true" size={22} />
                重新讀取
              </button>
            </div>
          )}

          {!listLoading && !listError && invitations.length === 0 && (
            <div
              style={{
                background: 'var(--state-candidate-bg)',
                borderRadius: 'var(--radius-md)',
                marginTop: 'var(--space-5)',
                padding: 'var(--space-6)',
                textAlign: 'center',
              }}
            >
              <Ticket
                aria-hidden="true"
                color="var(--state-candidate-fg)"
                size={42}
                weight="duotone"
              />
              <p style={{ color: 'var(--color-muted-foreground)', marginBottom: 0 }}>
                目前沒有邀請紀錄。建立第一組邀請碼後會顯示在這裡。
              </p>
            </div>
          )}

          {!listLoading && !listError && invitations.length > 0 && (
            <ul style={{ display: 'grid', gap: 'var(--space-3)', listStyle: 'none', margin: 'var(--space-5) 0 0', padding: 0 }}>
              {invitations.map((item) => {
                const isRevoking = revokingId === item.invitation_id;
                const isConfirming = confirmRevokeId === item.invitation_id;
                return (
                  <li
                    key={item.invitation_id}
                    style={{
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-md)',
                      padding: 'var(--space-4)',
                    }}
                  >
                    <div
                      style={{
                        alignItems: 'flex-start',
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: 'var(--space-3)',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <InvitationStatusBadge status={item.status} />
                        <p style={{ fontSize: 'var(--text-sm)', margin: 'var(--space-3) 0 var(--space-1)' }}>
                          建立：{formatDate(item.created_at)}
                        </p>
                        <p style={{ color: 'var(--color-muted-foreground)', fontSize: 'var(--text-sm)', margin: 0 }}>
                          到期：{formatDate(item.expires_at)}
                        </p>
                      </div>
                      {item.status === 'ISSUED' && !isConfirming && (
                        <button
                          disabled={revokingId !== null}
                          onClick={() => {
                            setConfirmRevokeId(item.invitation_id);
                            setActionError(null);
                          }}
                          style={secondaryButtonStyle}
                          type="button"
                        >
                          <Trash aria-hidden="true" size={22} />
                          撤銷
                        </button>
                      )}
                    </div>

                    <div
                      style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: 'var(--space-2)',
                        marginTop: 'var(--space-3)',
                      }}
                    >
                      {item.share_scope.map((scope) => (
                        <span
                          key={scope}
                          style={{
                            background: 'var(--color-primary-weak)',
                            borderRadius: 'var(--radius-full)',
                            color: 'var(--color-primary-text)',
                            fontSize: 'var(--text-sm)',
                            padding: 'var(--space-1) var(--space-2)',
                          }}
                        >
                          {SCOPE_LABELS[scope]}
                        </span>
                      ))}
                    </div>

                    {isConfirming && (
                      <div
                        aria-labelledby={`revoke-title-${item.invitation_id}`}
                        role="alertdialog"
                        style={{
                          background: 'var(--state-withdrawn-bg)',
                          border: '1px solid var(--state-withdrawn-fg)',
                          borderRadius: 'var(--radius-md)',
                          marginTop: 'var(--space-4)',
                          padding: 'var(--space-4)',
                        }}
                      >
                        <h3 id={`revoke-title-${item.invitation_id}`} style={{ fontSize: 'var(--text-base)', marginTop: 0 }}>
                          確定撤銷這組邀請嗎？
                        </h3>
                        <p style={{ lineHeight: 'var(--leading-body)' }}>
                          撤銷後，家屬將無法再使用這組邀請碼，而且無法復原。
                        </p>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
                          <button
                            disabled={isRevoking}
                            onClick={() => void revoke(item.invitation_id)}
                            style={{ ...primaryButtonStyle, background: 'var(--color-destructive)' }}
                            type="button"
                          >
                            {isRevoking ? (
                              <SpinnerGap aria-hidden="true" className="spin" size={22} />
                            ) : (
                              <Trash aria-hidden="true" size={22} />
                            )}
                            {isRevoking ? '正在撤銷…' : '確定撤銷'}
                          </button>
                          <button
                            disabled={isRevoking}
                            onClick={() => setConfirmRevokeId(null)}
                            style={secondaryButtonStyle}
                            type="button"
                          >
                            保留邀請
                          </button>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section
          style={{
            ...cardStyle,
            alignItems: 'flex-start',
            background: 'var(--state-published-bg)',
            display: 'flex',
            gap: 'var(--space-3)',
          }}
        >
          <LockKey aria-hidden="true" color="var(--color-primary-text)" size={30} weight="fill" />
          <div>
            <strong>分享範圍由你決定</strong>
            <p style={{ lineHeight: 'var(--leading-body)', marginBottom: 0 }}>
              邀請只會分享你已同意的摘要，不會讓家屬取得你的登入權限，也不會顯示完整私人對話。
            </p>
          </div>
        </section>
      </div>

      <p style={{ marginTop: 'var(--space-8)' }}>
        <Link
          href="/"
          style={{ alignItems: 'center', color: 'var(--color-primary-text)', display: 'inline-flex', gap: 8 }}
        >
          <ArrowLeft aria-hidden="true" size={24} />
          返回長者首頁
        </Link>
      </p>
    </main>
  );
}
