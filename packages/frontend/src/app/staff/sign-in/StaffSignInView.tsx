'use client';

import { type FormEvent, useState } from 'react';
import { AuthSubmitButton } from '@/components/AuthSubmitButton';
import { PasswordInput } from '@/components/auth/PasswordInput';
import { useLocale } from '@/lib/i18n/locale-context';

const inputStyle = {
  boxSizing: 'border-box' as const,
  fontSize: 18,
  marginBottom: 16,
  padding: 12,
  width: '100%',
};

export function StaffSignInView({
  nativeEnabled,
  showLine,
}: {
  nativeEnabled: boolean;
  showLine: boolean;
}) {
  const { t } = useLocale();
  const [pendingProvider, setPendingProvider] = useState<'password' | 'google' | 'line' | null>(
    null,
  );
  const isSubmitting = pendingProvider !== null;

  const submitAfterPendingPaint = (
    event: FormEvent<HTMLFormElement>,
    provider: 'password' | 'google' | 'line',
  ) => {
    event.preventDefault();
    if (isSubmitting) return;

    const form = event.currentTarget;
    setPendingProvider(provider);
    requestAnimationFrame(() => form.submit());
  };

  return (
    <main style={{ margin: '80px auto', maxWidth: 520, padding: 24, textAlign: 'center' }}>
      <h1 style={{ fontSize: 28 }}>{t('staffSignIn.title')}</h1>
      <p style={{ color: 'var(--color-foreground)', lineHeight: 1.7, margin: '20px 0' }}>
        {t('staffSignIn.body')}
      </p>
      <form
        action={nativeEnabled ? '/backend/auth/kinsun/login' : '/backend/auth/login'}
        method="post"
        onSubmit={(event) => submitAfterPendingPaint(event, nativeEnabled ? 'password' : 'google')}
      >
        {!nativeEnabled && <input name="intent" type="hidden" value="STAFF" />}
        {!nativeEnabled && <input name="provider" type="hidden" value="GOOGLE" />}
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        {nativeEnabled && (
          <>
            <input
              aria-label="工作 Email"
              autoComplete="email"
              maxLength={254}
              name="email"
              placeholder="工作 Email / Work email"
              required
              style={inputStyle}
              type="email"
            />
            <PasswordInput
              ariaLabel="密碼"
              autoComplete="current-password"
              maxLength={128}
              minLength={12}
              name="password"
              placeholder="密碼 / Password"
              required
              style={inputStyle}
            />
          </>
        )}
        <AuthSubmitButton
          disabled={isSubmitting}
          pending={pendingProvider === (nativeEnabled ? 'password' : 'google')}
          pendingLabel={nativeEnabled ? t('common.signingIn') : t('common.redirecting')}
        >
          {nativeEnabled ? '登入 / Sign in' : t('common.continueWithGoogle')}
        </AuthSubmitButton>
      </form>
      {showLine && (
        <form
          action="/backend/auth/login"
          method="post"
          onSubmit={(event) => submitAfterPendingPaint(event, 'line')}
          style={{ marginTop: 'var(--space-4)' }}
        >
          <input name="intent" type="hidden" value="STAFF" />
          <input name="provider" type="hidden" value="LINE" />
          <input name="returnTo" type="hidden" value="/onboarding/resolve" />
          <button
            aria-busy={pendingProvider === 'line'}
            aria-live="polite"
            disabled={isSubmitting}
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border-strong)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-primary-text)',
              cursor: isSubmitting ? 'wait' : 'pointer',
              fontFamily: 'inherit',
              fontSize: 'var(--text-base)',
              minHeight: 'var(--touch-min)',
              opacity: isSubmitting ? 0.72 : 1,
              padding: 'var(--space-3) var(--space-6)',
            }}
            type="submit"
          >
            {pendingProvider === 'line' ? t('common.redirecting') : t('staffSignIn.lineButton')}
          </button>
        </form>
      )}
      {showLine && (
        <p style={{ color: 'var(--color-foreground)', marginTop: 'var(--space-3)' }}>
          {t('staffSignIn.lineHint')}
        </p>
      )}
      <p style={{ color: 'var(--color-foreground)', marginTop: 24 }}>
        {t('staffSignIn.notActivated')}
      </p>
      <p style={{ color: 'var(--color-foreground)', marginTop: 12 }}>
        工作人員帳號由機構建立，不開放自行註冊。Staff accounts are organization-provisioned.
      </p>
    </main>
  );
}
