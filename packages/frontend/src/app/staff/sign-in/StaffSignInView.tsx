'use client';

import { type FormEvent, useState } from 'react';
import { AuthSubmitButton } from '@/components/AuthSubmitButton';
import { AuthField } from '@/components/auth/AuthField';
import { useLocale } from '@/lib/i18n/locale-context';

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
          /* Visible labels, not placeholder-only ones: a placeholder disappears
             as soon as the worker starts typing. Same AuthField as /elder/start. */
          <div style={{ marginBottom: 'var(--space-4)', textAlign: 'left' }}>
            <AuthField
              autoComplete="email"
              label={t('staffSignIn.emailLabel')}
              maxLength={254}
              name="email"
              required
              type="email"
            />
            <AuthField
              autoComplete="current-password"
              hidePasswordLabel={t('authLayout.hidePassword')}
              label={t('common.password')}
              maxLength={128}
              minLength={12}
              name="password"
              required
              showPasswordLabel={t('authLayout.showPassword')}
              type="password"
            />
          </div>
        )}
        <AuthSubmitButton
          disabled={isSubmitting}
          pending={pendingProvider === (nativeEnabled ? 'password' : 'google')}
          pendingLabel={nativeEnabled ? t('common.signingIn') : t('common.redirecting')}
        >
          {nativeEnabled ? t('authLayout.signIn') : t('common.continueWithGoogle')}
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
        {t('staffSignIn.provisioned')}
      </p>
    </main>
  );
}
