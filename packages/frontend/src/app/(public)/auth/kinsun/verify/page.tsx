import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import {
  kinsunChallengeCookieName,
  normalizeKinsunChallenge,
} from '@/lib/server/kinsun-auth-cookie';
import { kinsunNativeAuthEnabled } from '@/lib/server/kinsun-auth-core';

export const dynamic = 'force-dynamic';

const inputStyle = {
  boxSizing: 'border-box' as const,
  fontSize: 'var(--text-base)',
  marginTop: 8,
  minHeight: 'var(--touch-min)',
  padding: 14,
  width: '100%',
};

export default async function KinsunEmailVerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  if (!kinsunNativeAuthEnabled()) redirect('/sign-in');
  const [params, cookieStore] = await Promise.all([searchParams, cookies()]);
  if (!normalizeKinsunChallenge(cookieStore.get(kinsunChallengeCookieName())?.value)) {
    redirect('/sign-in?error=challenge_missing');
  }

  return (
    <main style={{ margin: '0 auto', maxWidth: 560, padding: 'var(--space-6)' }}>
      <h1 style={{ fontSize: 'var(--text-2xl)' }}>驗證 Email 並設定密碼</h1>
      <p style={{ lineHeight: 1.7 }}>
        請輸入收到的六位數驗證碼，再設定您的 Kinsun 密碼。This code verifies your email;
        future sign-ins use your password.
      </p>
      {params.error && (
        <p role="alert" style={{ color: 'var(--color-destructive)' }}>
          {params.error === 'invalid'
            ? '驗證碼或密碼格式不正確，請重新確認。'
            : '註冊服務暫時無法使用，請稍後再試。'}
        </p>
      )}
      <form action="/backend/auth/kinsun/complete" method="post">
        <label htmlFor="verificationCode" style={{ display: 'block', fontWeight: 700 }}>
          Email 驗證碼 / Verification code
        </label>
        <input
          autoComplete="one-time-code"
          id="verificationCode"
          inputMode="numeric"
          maxLength={6}
          minLength={6}
          name="verificationCode"
          pattern="[0-9]{6}"
          required
          style={{ ...inputStyle, fontSize: 24 }}
        />
        <label
          htmlFor="password"
          style={{ display: 'block', fontWeight: 700, marginTop: 'var(--space-4)' }}
        >
          密碼 / Password
        </label>
        <input
          autoComplete="new-password"
          id="password"
          maxLength={128}
          minLength={12}
          name="password"
          required
          style={inputStyle}
          type="password"
        />
        <p style={{ fontSize: 'var(--text-sm)', lineHeight: 1.6 }}>
          至少 12 個字元。Use at least 12 characters.
        </p>
        <label
          htmlFor="passwordConfirmation"
          style={{ display: 'block', fontWeight: 700, marginTop: 'var(--space-4)' }}
        >
          再輸入一次密碼 / Confirm password
        </label>
        <input
          autoComplete="new-password"
          id="passwordConfirmation"
          maxLength={128}
          minLength={12}
          name="passwordConfirmation"
          required
          style={inputStyle}
          type="password"
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
            padding: 'var(--space-3) var(--space-5)',
            width: '100%',
          }}
          type="submit"
        >
          建立帳號並登入 / Create account
        </button>
      </form>
    </main>
  );
}
