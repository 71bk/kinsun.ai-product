'use client';

import {
  ArrowClockwise,
  ArrowLeft,
  CheckCircle,
  ChatCircleDots,
  ClockCountdown,
  LinkBreak,
  LinkSimple,
  LockKey,
  ShieldCheck,
  SignIn,
  SpinnerGap,
  WarningCircle,
  XCircle,
} from '@phosphor-icons/react';
import Link from 'next/link';
import { useCallback, useEffect, useState, type CSSProperties, type FormEvent } from 'react';
import { hasAuthCredential } from '@/lib/auth-session';
import { ApiRequestError } from '@/lib/api/client';
import { getLineLinkStatus, unlinkLineAccount, type LineLinkStatus } from '@/lib/api/line-link';

interface LineAccountLinkClientProps {
  hasPendingLinkToken: boolean;
  initialNotice?: 'already_linked';
  initialError?: 'invalid_link' | 'link_expired' | 'link_failed' | 'service_unavailable';
}

const apiConfig = { apiBaseUrl: '/backend/core' };

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

const destructiveButtonStyle: CSSProperties = {
  ...primaryButtonStyle,
  background: 'var(--color-destructive)',
};

function InitialFeedback({ error }: { error: LineAccountLinkClientProps['initialError'] }) {
  if (!error) return null;

  const feedback = {
    invalid_link: {
      Icon: XCircle,
      title: '這個連結無效',
      message: '為了保護帳號安全，無效連結不會繼續處理。請回到 LINE 重新取得連結。',
    },
    link_expired: {
      Icon: ClockCountdown,
      title: '連結已逾時',
      message: 'LINE 連結有安全時效，請回到官方帳號重新輸入「連結帳號」。',
    },
    link_failed: {
      Icon: WarningCircle,
      title: '這次沒有完成連結',
      message: '帳號沒有被變更。請回到 LINE 重新輸入「連結帳號」再試一次。',
    },
    service_unavailable: {
      Icon: WarningCircle,
      title: '服務暫時忙碌',
      message: '你的短效連結仍安全保留。請稍後使用下方按鈕再試一次。',
    },
  }[error];
  const Icon = feedback.Icon;

  return (
    <section
      aria-live="polite"
      role="alert"
      style={{
        ...cardStyle,
        alignItems: 'flex-start',
        background: 'var(--state-review-bg)',
        borderColor: 'var(--state-review-fg)',
        display: 'flex',
        gap: 'var(--space-3)',
      }}
    >
      <Icon aria-hidden="true" color="var(--state-review-fg)" size={30} weight="fill" />
      <div>
        <h2 style={{ fontSize: 'var(--text-lg)', margin: 0 }}>{feedback.title}</h2>
        <p style={{ lineHeight: 'var(--leading-body)', marginBottom: 0 }}>{feedback.message}</p>
      </div>
    </section>
  );
}

export function LineAccountLinkClient({
  hasPendingLinkToken,
  initialNotice,
  initialError,
}: LineAccountLinkClientProps) {
  const [credential, setCredential] = useState<'loading' | 'present' | 'missing' | 'unavailable'>(
    'loading',
  );
  const [linkStatus, setLinkStatus] = useState<LineLinkStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    setError(null);
    try {
      setLinkStatus(await getLineLinkStatus(apiConfig));
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 401) {
        setCredential('missing');
      } else {
        setError('目前無法讀取 LINE 連結狀態，請稍後再試。');
      }
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void hasAuthCredential()
      .then(async (present) => {
        if (cancelled) return;
        setCredential(present ? 'present' : 'missing');
        if (present) await loadStatus();
      })
      .catch(() => {
        if (!cancelled) setCredential('unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, [loadStatus]);

  async function unlink() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setLinkStatus(await unlinkLineAccount(apiConfig));
      setConfirmUnlink(false);
      setNotice('LINE 連結已安全解除。之後仍可從 LINE 重新連結。');
    } catch {
      setError('目前無法解除 LINE 連結，帳號沒有被變更，請稍後再試。');
    } finally {
      setBusy(false);
    }
  }

  function submitLink(event: FormEvent<HTMLFormElement>) {
    if (busy) {
      event.preventDefault();
      return;
    }
    setBusy(true);
    setError(null);
  }

  const showInitialFeedback = initialError && !linkStatus?.linked;

  return (
    <main
      data-surface="voice"
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
            color: 'var(--color-accent-text)',
            display: 'flex',
            fontSize: 'var(--text-sm)',
            fontWeight: 700,
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-2)',
          }}
        >
          <ShieldCheck aria-hidden="true" size={26} weight="fill" />
          安全的帳號連結
        </div>
        <h1 style={{ fontSize: 'var(--text-2xl)', lineHeight: 1.25, margin: 0 }}>LINE 帳號連結</h1>
        <p
          style={{
            color: 'var(--color-muted-foreground)',
            fontSize: 'var(--text-base)',
            lineHeight: 'var(--leading-body)',
            marginBottom: 0,
          }}
        >
          長者可在 LINE
          使用陪伴服務；家屬可接收已發布照護摘要的最小通知。系統每次都會重新確認身分、授權與同意狀態。
        </p>
      </header>

      <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
        {initialNotice === 'already_linked' && (
          <section
            aria-live="polite"
            style={{
              ...cardStyle,
              alignItems: 'flex-start',
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
            <div>
              <strong>已經完成連結</strong>
              <p style={{ lineHeight: 'var(--leading-body)', margin: 'var(--space-1) 0 0' }}>
                此 kinsun.ai 帳號已連結 LINE，不需要重複操作。
              </p>
            </div>
          </section>
        )}

        {showInitialFeedback && <InitialFeedback error={initialError} />}

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

        {error && (
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
              <XCircle
                aria-hidden="true"
                color="var(--state-withdrawn-fg)"
                size={30}
                weight="fill"
              />
              <div style={{ flex: 1 }}>
                <strong>操作沒有完成</strong>
                <p
                  style={{
                    lineHeight: 'var(--leading-body)',
                    margin: 'var(--space-1) 0 var(--space-4)',
                  }}
                >
                  {error}
                </p>
                {credential === 'present' && !linkStatus && (
                  <button
                    disabled={statusLoading}
                    onClick={() => void loadStatus()}
                    style={secondaryButtonStyle}
                    type="button"
                  >
                    {statusLoading ? (
                      <SpinnerGap aria-hidden="true" className="spin" size={24} />
                    ) : (
                      <ArrowClockwise aria-hidden="true" size={24} />
                    )}
                    重新讀取狀態
                  </button>
                )}
              </div>
            </div>
          </section>
        )}

        {(credential === 'loading' ||
          (credential === 'present' && statusLoading && !linkStatus)) && (
          <section aria-live="polite" aria-busy="true" style={cardStyle}>
            <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
              <SpinnerGap aria-hidden="true" className="spin" size={30} />
              <p style={{ margin: 0 }}>正在安全地確認登入與連結狀態…</p>
            </div>
          </section>
        )}

        {credential === 'unavailable' && (
          <section role="alert" style={{ ...cardStyle, background: 'var(--state-withdrawn-bg)' }}>
            <WarningCircle aria-hidden="true" size={30} weight="fill" />
            <h2 style={{ fontSize: 'var(--text-lg)' }}>目前無法確認登入狀態</h2>
            <p style={{ lineHeight: 'var(--leading-body)' }}>
              系統已安全停止，不會進行任何帳號連結。請重新整理頁面後再試。
            </p>
            <button
              onClick={() => window.location.reload()}
              style={secondaryButtonStyle}
              type="button"
            >
              <ArrowClockwise aria-hidden="true" size={24} />
              重新整理
            </button>
          </section>
        )}

        {credential === 'missing' && (
          <section style={{ ...cardStyle, background: 'var(--state-published-bg)' }}>
            <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
              <SignIn
                aria-hidden="true"
                color="var(--color-primary-text)"
                size={32}
                weight="fill"
              />
              <h2 style={{ fontSize: 'var(--text-xl)', margin: 0 }}>請先登入 kinsun.ai</h2>
            </div>
            <p style={{ lineHeight: 'var(--leading-body)' }}>
              登入完成後會自動回到這一頁，繼續剛才的 LINE 連結。短效連結不會顯示在網址中。
            </p>
            <div
              style={{
                alignItems: 'flex-start',
                background: 'var(--color-surface)',
                borderRadius: 'var(--radius-md)',
                display: 'flex',
                gap: 'var(--space-2)',
                marginBottom: 'var(--space-5)',
                padding: 'var(--space-3)',
              }}
            >
              <LockKey aria-hidden="true" color="var(--color-primary-text)" size={26} />
              <small style={{ fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-body)' }}>
                我們只會使用登入資訊確認身分，不會把 LINE 的連結憑證放在瀏覽器網址。
              </small>
            </div>
            <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
              <form action="/backend/auth/login" method="post">
                <input name="intent" type="hidden" value="ELDER" />
                <input name="returnTo" type="hidden" value="/line/account-link" />
                <button style={{ ...primaryButtonStyle, width: '100%' }} type="submit">
                  <SignIn aria-hidden="true" size={26} />
                  以長者身分登入並繼續
                </button>
              </form>
              <form action="/backend/auth/login" method="post">
                <input name="intent" type="hidden" value="FAMILY" />
                <input name="returnTo" type="hidden" value="/line/account-link" />
                <button style={{ ...secondaryButtonStyle, width: '100%' }} type="submit">
                  <SignIn aria-hidden="true" size={26} />
                  以家屬身分登入並繼續
                </button>
              </form>
            </div>
          </section>
        )}

        {credential === 'present' && linkStatus?.linked && (
          <section
            aria-labelledby="line-linked-title"
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
                size={38}
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
                  連結狀態
                </div>
                <h2 id="line-linked-title" style={{ fontSize: 'var(--text-xl)', margin: 0 }}>
                  LINE 已連結成功
                </h2>
              </div>
            </div>
            <p style={{ lineHeight: 'var(--leading-body)' }}>
              現在可以回到 LINE 官方帳號。長者可使用陪伴服務；家屬可接收已發布摘要通知。
            </p>
            {linkStatus.linked_at && (
              <p style={{ color: 'var(--color-muted-foreground)', fontSize: 'var(--text-sm)' }}>
                連結時間：{new Date(linkStatus.linked_at).toLocaleString('zh-TW')}
              </p>
            )}

            {linkStatus.can_unlink && !confirmUnlink && (
              <button
                disabled={busy}
                onClick={() => {
                  setConfirmUnlink(true);
                  setError(null);
                }}
                style={secondaryButtonStyle}
                type="button"
              >
                <LinkBreak aria-hidden="true" size={24} />
                解除 LINE 連結
              </button>
            )}

            {linkStatus.can_unlink && confirmUnlink && (
              <div
                aria-labelledby="unlink-confirm-title"
                role="alertdialog"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--state-withdrawn-fg)',
                  borderRadius: 'var(--radius-md)',
                  marginTop: 'var(--space-5)',
                  padding: 'var(--space-4)',
                }}
              >
                <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-2)' }}>
                  <WarningCircle
                    aria-hidden="true"
                    color="var(--state-withdrawn-fg)"
                    size={28}
                    weight="fill"
                  />
                  <h3 id="unlink-confirm-title" style={{ fontSize: 'var(--text-lg)', margin: 0 }}>
                    確定要解除連結嗎？
                  </h3>
                </div>
                <p style={{ lineHeight: 'var(--leading-body)' }}>
                  解除後，這個 LINE
                  帳號將無法再使用陪伴服務或接收家屬通知；既有照護資料不會因此被刪除。
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
                  <button
                    disabled={busy}
                    onClick={() => void unlink()}
                    style={destructiveButtonStyle}
                    type="button"
                  >
                    {busy ? (
                      <SpinnerGap aria-hidden="true" className="spin" size={24} />
                    ) : (
                      <LinkBreak aria-hidden="true" size={24} />
                    )}
                    {busy ? '正在解除…' : '確定解除'}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => setConfirmUnlink(false)}
                    style={secondaryButtonStyle}
                    type="button"
                  >
                    保留連結
                  </button>
                </div>
              </div>
            )}

            {!linkStatus.can_unlink && (
              <p style={{ color: 'var(--color-muted-foreground)', fontSize: 'var(--text-sm)' }}>
                此連結目前無法在這裡解除；如需協助，請聯絡服務人員。
              </p>
            )}
          </section>
        )}

        {credential === 'present' &&
          linkStatus &&
          !linkStatus.linked &&
          hasPendingLinkToken &&
          initialError !== 'invalid_link' &&
          initialError !== 'link_expired' &&
          initialError !== 'link_failed' && (
            <section aria-labelledby="complete-line-link-title" style={cardStyle}>
              <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
                <LinkSimple aria-hidden="true" color="var(--color-primary-text)" size={34} />
                <div>
                  <div
                    style={{
                      color: 'var(--color-primary-text)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 700,
                    }}
                  >
                    連結前確認
                  </div>
                  <h2
                    id="complete-line-link-title"
                    style={{ fontSize: 'var(--text-xl)', margin: 0 }}
                  >
                    完成 LINE 連結
                  </h2>
                </div>
              </div>
              <p style={{ lineHeight: 'var(--leading-body)' }}>
                按下按鈕後會前往 LINE 官方確認畫面。請確認目前登入的是要連結的 kinsun.ai 帳號。
              </p>
              <ul style={{ lineHeight: 'var(--leading-body)', paddingLeft: '1.4em' }}>
                <li>連結只用來辨識目前帳號：長者用於陪伴，家屬用於通知。</li>
                <li>不會讀取其他 LINE 聊天室或聯絡人。</li>
                <li>完成後可隨時回到本頁解除連結。</li>
              </ul>
              <form
                action="/backend/line/account-link/complete"
                method="post"
                onSubmit={submitLink}
              >
                <button
                  disabled={busy}
                  style={{
                    ...primaryButtonStyle,
                    background: 'var(--color-accent)',
                    width: '100%',
                  }}
                  type="submit"
                >
                  {busy ? (
                    <SpinnerGap aria-hidden="true" className="spin" size={28} />
                  ) : initialError === 'service_unavailable' ? (
                    <ArrowClockwise aria-hidden="true" size={28} />
                  ) : (
                    <LinkSimple aria-hidden="true" size={28} />
                  )}
                  {busy
                    ? '正在前往 LINE…'
                    : initialError === 'service_unavailable'
                      ? '重新嘗試連結'
                      : '前往 LINE 確認連結'}
                </button>
              </form>
            </section>
          )}

        {credential === 'present' &&
          linkStatus &&
          !linkStatus.linked &&
          (!hasPendingLinkToken ||
            initialError === 'invalid_link' ||
            initialError === 'link_expired' ||
            initialError === 'link_failed') && (
            <section aria-labelledby="line-unlinked-title" style={cardStyle}>
              <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
                <LinkBreak aria-hidden="true" color="var(--color-muted-foreground)" size={34} />
                <div>
                  <div
                    style={{
                      color: 'var(--color-muted-foreground)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 700,
                    }}
                  >
                    連結狀態
                  </div>
                  <h2 id="line-unlinked-title" style={{ fontSize: 'var(--text-xl)', margin: 0 }}>
                    尚未連結 LINE
                  </h2>
                </div>
              </div>
              <p style={{ lineHeight: 'var(--leading-body)' }}>
                請回到 kinsun.ai LINE 官方帳號，輸入「連結帳號」，再按 LINE 傳來的連結按鈕。
              </p>
              <button
                disabled={statusLoading}
                onClick={() => void loadStatus()}
                style={secondaryButtonStyle}
                type="button"
              >
                {statusLoading ? (
                  <SpinnerGap aria-hidden="true" className="spin" size={24} />
                ) : (
                  <ArrowClockwise aria-hidden="true" size={24} />
                )}
                我已操作，重新檢查狀態
              </button>
            </section>
          )}

        <section aria-labelledby="line-guide-title" style={cardStyle}>
          <div style={{ alignItems: 'center', display: 'flex', gap: 'var(--space-3)' }}>
            <ChatCircleDots aria-hidden="true" color="var(--color-primary-text)" size={34} />
            <h2 id="line-guide-title" style={{ fontSize: 'var(--text-xl)', margin: 0 }}>
              LINE Bot 使用說明
            </h2>
          </div>
          <ol
            style={{
              display: 'grid',
              gap: 'var(--space-4)',
              lineHeight: 'var(--leading-body)',
              listStyle: 'none',
              padding: 0,
            }}
          >
            {[
              ['1', '取得安全連結', '在 kinsun.ai LINE 官方帳號輸入「連結帳號」。'],
              ['2', '確認本人身分', '開啟 LINE 傳來的按鈕，登入後在本頁確認連結。'],
              ['3', '開始陪伴對話', '連結成功後回到 LINE，輸入想聊的內容即可開始。'],
            ].map(([step, title, description]) => (
              <li
                key={step}
                style={{ alignItems: 'flex-start', display: 'flex', gap: 'var(--space-3)' }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    alignItems: 'center',
                    background: 'var(--color-primary-weak)',
                    borderRadius: 'var(--radius-full)',
                    color: 'var(--color-primary-text)',
                    display: 'inline-flex',
                    flex: '0 0 var(--touch-min)',
                    fontWeight: 800,
                    height: 'var(--touch-min)',
                    justifyContent: 'center',
                  }}
                >
                  {step}
                </span>
                <div>
                  <strong>{title}</strong>
                  <p
                    style={{ color: 'var(--color-muted-foreground)', margin: 'var(--space-1) 0 0' }}
                  >
                    {description}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <div
            style={{
              alignItems: 'flex-start',
              background: 'var(--state-review-bg)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              gap: 'var(--space-2)',
              padding: 'var(--space-3)',
            }}
          >
            <ShieldCheck aria-hidden="true" color="var(--state-review-fg)" size={26} />
            <small style={{ fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-body)' }}>
              LINE 不會取代緊急服務。遇到身體不適或緊急狀況，請直接聯絡照護人員或當地緊急服務。
            </small>
          </div>
        </section>
      </div>

      <p style={{ marginTop: 'var(--space-8)' }}>
        <Link
          href="/"
          style={{
            alignItems: 'center',
            color: 'var(--color-primary-text)',
            display: 'inline-flex',
            gap: 8,
          }}
        >
          <ArrowLeft aria-hidden="true" size={24} />
          返回長者首頁
        </Link>
      </p>
    </main>
  );
}
