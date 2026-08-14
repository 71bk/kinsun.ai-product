'use client';

import { AuthSubmitButton } from '@/components/AuthSubmitButton';
import { useLocale } from '@/lib/i18n/locale-context';

export function FamilySignInView({
  nativeEnabled,
  showLine,
}: {
  nativeEnabled: boolean;
  showLine: boolean;
}) {
  const { t } = useLocale();

  return (
    <main style={{ margin: '80px auto', maxWidth: 520, padding: 24, textAlign: 'center' }}>
      <h1 style={{ fontSize: 28 }}>{t('familySignIn.title')}</h1>
      <p style={{ color: 'var(--color-foreground)', lineHeight: 1.7, margin: '20px 0' }}>
        {t('familySignIn.body')}
      </p>
      <form action={nativeEnabled ? '/backend/auth/kinsun/start' : '/backend/auth/login'} method="post">
        <input name="intent" type="hidden" value="FAMILY" />
        {!nativeEnabled && <input name="provider" type="hidden" value="GOOGLE" />}
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        {nativeEnabled && (
          <input
            autoComplete="email"
            maxLength={254}
            name="email"
            placeholder="Email"
            required
            style={{ boxSizing: 'border-box', fontSize: 18, marginBottom: 16, padding: 12, width: '100%' }}
            type="email"
          />
        )}
        <AuthSubmitButton>
          {nativeEnabled ? '傳送 Email 驗證碼' : t('common.continueWithGoogle')}
        </AuthSubmitButton>
      </form>
      {showLine && (
        <form action="/backend/auth/login" method="post" style={{ marginTop: 'var(--space-4)' }}>
          <input name="intent" type="hidden" value="FAMILY" />
          <input name="provider" type="hidden" value="LINE" />
          <input name="returnTo" type="hidden" value="/onboarding/resolve" />
          <button
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border-strong)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-primary-text)',
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: 'var(--text-base)',
              minHeight: 'var(--touch-min)',
              padding: 'var(--space-3) var(--space-6)',
            }}
            type="submit"
          >
            {t('familySignIn.lineButton')}
          </button>
        </form>
      )}
      {showLine && (
        <p style={{ color: 'var(--color-foreground)', marginTop: 'var(--space-3)' }}>
          {t('familySignIn.lineHint')}
        </p>
      )}
    </main>
  );
}
