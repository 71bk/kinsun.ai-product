import { touchLinkStyle } from '@/components/touch-link';

export const dynamic = 'force-dynamic';

const inputStyle = {
  boxSizing: 'border-box' as const,
  fontSize: 'var(--text-base)',
  minHeight: 'var(--touch-min)',
  padding: 'var(--space-3)',
  width: '100%',
};

export default function ElderStartPage() {
  const nativeEnabled =
    process.env.KINSUN_NATIVE_AUTH_ENABLED?.trim().toLowerCase() === 'true';
  const showGoogle = process.env.GOOGLE_DIRECT_OIDC_ENABLED?.trim().toLowerCase() === 'true';
  const showLine = process.env.LINE_DIRECT_OIDC_ENABLED?.trim().toLowerCase() === 'true';

  return (
    <main style={{ margin: '0 auto', maxWidth: 640, padding: 'var(--space-6)' }}>
      <h1 style={{ fontSize: 'var(--text-2xl)', lineHeight: 1.4 }}>建立或登入 Kinsun 帳號</h1>
      <p style={{ lineHeight: 'var(--leading-body)', margin: 'var(--space-4) 0' }}>
        使用您的 Email 接收驗證碼，不需要設定密碼。第一次驗證會建立您的 Kinsun 帳號。
      </p>
      {nativeEnabled && (
        <form action="/backend/auth/kinsun/start" method="post">
          <input name="intent" type="hidden" value="ELDER" />
          <input name="returnTo" type="hidden" value="/onboarding/resolve" />
          <label htmlFor="displayName" style={{ display: 'block', fontWeight: 700 }}>
            稱呼（第一次註冊時使用）
          </label>
          <input id="displayName" maxLength={120} name="displayName" style={inputStyle} />
          <label
            htmlFor="email"
            style={{ display: 'block', fontWeight: 700, marginTop: 'var(--space-4)' }}
          >
            Email
          </label>
          <input
            autoComplete="email"
            id="email"
            maxLength={254}
            name="email"
            required
            style={inputStyle}
            type="email"
          />
          <button
            style={{
              background: 'var(--color-primary-strong)',
              border: 0,
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-on-primary)',
              fontSize: 'var(--text-lg)',
              marginTop: 'var(--space-4)',
              minHeight: 'var(--touch-min)',
              padding: 'var(--space-4) var(--space-5)',
              width: '100%',
            }}
            type="submit"
          >
            傳送驗證碼
          </button>
        </form>
      )}
      {(showGoogle || showLine) && (
        <section style={{ borderTop: '1px solid var(--color-border-strong)', marginTop: 28, paddingTop: 20 }}>
          <p>已綁定第三方登入方式的帳號，也可以繼續使用：</p>
          {showGoogle && (
            <form action="/backend/auth/login" method="post">
              <input name="intent" type="hidden" value="ELDER" />
              <input name="provider" type="hidden" value="GOOGLE" />
              <input name="returnTo" type="hidden" value="/onboarding/resolve" />
              <button style={{ minHeight: 'var(--touch-min)', width: '100%' }} type="submit">
                使用已綁定的 Google 登入
              </button>
            </form>
          )}
          {showLine && (
            <form action="/backend/auth/login" method="post" style={{ marginTop: 12 }}>
              <input name="intent" type="hidden" value="ELDER" />
              <input name="provider" type="hidden" value="LINE" />
              <input name="returnTo" type="hidden" value="/onboarding/resolve" />
              <button style={{ minHeight: 'var(--touch-min)', width: '100%' }} type="submit">
                使用已綁定的 LINE 登入
              </button>
            </form>
          )}
        </section>
      )}
      <a href="/sign-in" style={touchLinkStyle}>
        返回角色選擇
      </a>
    </main>
  );
}
