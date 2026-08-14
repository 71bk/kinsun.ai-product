import { touchLinkStyle } from '@/components/touch-link';

export const dynamic = 'force-dynamic';

const inputStyle = {
  boxSizing: 'border-box' as const,
  fontSize: 'var(--text-base)',
  minHeight: 'var(--touch-min)',
  padding: 'var(--space-3)',
  width: '100%',
};

const primaryButtonStyle = {
  background: 'var(--color-primary-strong)',
  border: 0,
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-on-primary)',
  fontSize: 'var(--text-lg)',
  marginTop: 'var(--space-4)',
  minHeight: 'var(--touch-min)',
  padding: 'var(--space-4) var(--space-5)',
  width: '100%',
};

export default function ElderStartPage() {
  const nativeEnabled = process.env.KINSUN_NATIVE_AUTH_ENABLED?.trim().toLowerCase() === 'true';
  const showGoogle = process.env.GOOGLE_DIRECT_OIDC_ENABLED?.trim().toLowerCase() === 'true';
  const showLine = process.env.LINE_DIRECT_OIDC_ENABLED?.trim().toLowerCase() === 'true';

  return (
    <>
      <header
        style={{
          background: 'var(--color-surface)',
          borderBottom: '1px solid var(--color-border)',
          padding: 'var(--space-4) var(--space-6)',
        }}
      >
        <strong
          style={{ color: 'var(--color-foreground)', display: 'block', fontSize: 'var(--text-xl)' }}
        >
          小暖 Kinsun
        </strong>
        <span
          style={{
            color: 'var(--color-muted-foreground)',
            display: 'block',
            fontSize: 'var(--text-xs)',
            marginTop: 'var(--space-1)',
          }}
        >
          陪伴、同意與記憶都由您決定
        </span>
      </header>
      <main style={{ margin: '0 auto', maxWidth: 640, padding: 'var(--space-6)' }}>
        <h1 style={{ fontSize: 'var(--text-2xl)', lineHeight: 1.4 }}>登入 Kinsun / Sign in</h1>
        <p style={{ lineHeight: 'var(--leading-body)', margin: 'var(--space-4) 0' }}>
          已有自行使用帳號的長者可在這裡登入；日照中心建立的長者不需要另外申請帳號。
        </p>
        {nativeEnabled && (
          <>
            <form action="/backend/auth/kinsun/login" method="post">
              <input name="returnTo" type="hidden" value="/onboarding/resolve" />
              <label htmlFor="loginEmail" style={{ display: 'block', fontWeight: 700 }}>
                Email
              </label>
              <input
                autoComplete="email"
                id="loginEmail"
                maxLength={254}
                name="email"
                required
                style={inputStyle}
                type="email"
              />
              <label
                htmlFor="loginPassword"
                style={{ display: 'block', fontWeight: 700, marginTop: 'var(--space-4)' }}
              >
                密碼 / Password
              </label>
              <input
                autoComplete="current-password"
                id="loginPassword"
                maxLength={128}
                minLength={12}
                name="password"
                required
                style={inputStyle}
                type="password"
              />
              <button style={primaryButtonStyle} type="submit">
                登入 / Sign in
              </button>
            </form>

            <section
              style={{
                borderTop: '1px solid var(--color-border-strong)',
                marginTop: 32,
                paddingTop: 24,
              }}
            >
              <h2 style={{ fontSize: 'var(--text-xl)' }}>第一次自行使用？建立帳號</h2>
              <p>完成一次 Email 驗證後設定密碼。Create an account after email verification.</p>
              <form action="/backend/auth/kinsun/start" method="post">
                <input name="intent" type="hidden" value="ELDER" />
                <input name="returnTo" type="hidden" value="/onboarding/resolve" />
                <label htmlFor="displayName" style={{ display: 'block', fontWeight: 700 }}>
                  稱呼 / Display name
                </label>
                <input id="displayName" maxLength={120} name="displayName" style={inputStyle} />
                <label
                  htmlFor="registerEmail"
                  style={{ display: 'block', fontWeight: 700, marginTop: 'var(--space-4)' }}
                >
                  Email
                </label>
                <input
                  autoComplete="email"
                  id="registerEmail"
                  maxLength={254}
                  name="email"
                  required
                  style={inputStyle}
                  type="email"
                />
                <button style={primaryButtonStyle} type="submit">
                  傳送註冊驗證碼 / Send verification code
                </button>
              </form>
            </section>
          </>
        )}
        {(showGoogle || showLine) && (
          <section
            style={{
              borderTop: '1px solid var(--color-border-strong)',
              marginTop: 28,
              paddingTop: 20,
            }}
          >
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
          返回身分選擇 / Back
        </a>
      </main>
    </>
  );
}
