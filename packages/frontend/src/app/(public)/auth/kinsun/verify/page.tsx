import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { kinsunChallengeCookieName, normalizeKinsunChallenge } from '@/lib/server/kinsun-auth-cookie';
import { kinsunNativeAuthEnabled } from '@/lib/server/kinsun-auth-core';

export const dynamic = 'force-dynamic';

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
      <h1 style={{ fontSize: 'var(--text-2xl)' }}>輸入 Email 驗證碼</h1>
      <p style={{ lineHeight: 1.7 }}>
        驗證碼有效 10 分鐘。本機 QA 請使用專案環境設定中的測試碼；系統不會在網頁或 API 回傳測試碼。
      </p>
      {params.error && (
        <p role="alert" style={{ color: 'var(--color-destructive)' }}>
          {params.error === 'invalid'
            ? '驗證碼不正確或已失效，請再試一次。'
            : '登入服務暫時無法使用，請稍後再試。'}
        </p>
      )}
      <form action="/backend/auth/kinsun/complete" method="post">
        <label htmlFor="verificationCode" style={{ display: 'block', fontWeight: 700 }}>
          六位數驗證碼
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
          style={{ boxSizing: 'border-box', fontSize: 24, marginTop: 8, padding: 14, width: '100%' }}
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
          驗證並登入
        </button>
      </form>
    </main>
  );
}
