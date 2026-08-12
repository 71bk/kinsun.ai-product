'use client';

import Link from 'next/link';
import { AuthSubmitButton } from '@/components/AuthSubmitButton';
import { useLocale } from '@/lib/i18n/locale-context';

export function GoogleCompleteView({
  error,
  hasInvitation,
  intent,
  provider = 'GOOGLE',
}: {
  error: boolean;
  hasInvitation: boolean;
  intent: 'ELDER' | 'FAMILY';
  provider?: 'GOOGLE' | 'LINE';
}) {
  const { t } = useLocale();
  const family = intent === 'FAMILY';
  const line = provider === 'LINE';

  return (
    <main style={{ margin: '0 auto', maxWidth: 600, padding: 'var(--space-6)' }}>
      <h1 style={{ fontSize: 'var(--text-2xl)', lineHeight: 1.35 }}>
        {t(
          line
            ? family
              ? 'lineComplete.familyTitle'
              : 'lineComplete.elderTitle'
            : family
              ? 'googleComplete.familyTitle'
              : 'googleComplete.elderTitle',
        )}
      </h1>
      <p style={{ fontSize: 'var(--text-base)', lineHeight: 'var(--leading-body)' }}>
        {t(
          line
            ? family
              ? 'lineComplete.familyBody'
              : 'lineComplete.elderBody'
            : family
              ? 'googleComplete.familyBody'
              : 'googleComplete.elderBody',
        )}
      </p>
      {error && (
        <p role="alert" style={{ color: 'var(--color-destructive)', fontSize: 'var(--text-base)' }}>
          {t(line ? 'lineComplete.error' : 'googleComplete.error')}
        </p>
      )}
      {family && !hasInvitation ? (
        <div>
          <p
            role="alert"
            style={{ fontSize: 'var(--text-base)', lineHeight: 'var(--leading-body)' }}
          >
            {t(line ? 'lineComplete.missingInvitation' : 'googleComplete.missingInvitation')}
          </p>
          <Link href="/family/join">
            {t(line ? 'lineComplete.retryJoin' : 'googleComplete.retryJoin')}
          </Link>
        </div>
      ) : (
        <form
          action={line ? '/backend/auth/line/onboarding' : '/backend/auth/google/onboarding'}
          method="post"
        >
          {!family && (
            <label
              htmlFor="displayName"
              style={{ display: 'block', fontWeight: 700, marginBottom: 'var(--space-4)' }}
            >
              {t(line ? 'lineComplete.nameLabel' : 'googleComplete.nameLabel')}
              <input
                autoComplete="name"
                id="displayName"
                maxLength={120}
                name="displayName"
                required
                style={{
                  boxSizing: 'border-box',
                  display: 'block',
                  fontSize: 'var(--text-base)',
                  marginTop: 'var(--space-2)',
                  minHeight: 'var(--touch-min)',
                  padding: 'var(--space-3)',
                  width: '100%',
                }}
              />
            </label>
          )}
          <AuthSubmitButton>
            {t(
              line
                ? family
                  ? 'lineComplete.familySubmit'
                  : 'lineComplete.submit'
                : family
                  ? 'googleComplete.familySubmit'
                  : 'googleComplete.submit',
            )}
          </AuthSubmitButton>
        </form>
      )}
      <p
        style={{
          color: 'var(--color-foreground)',
          fontSize: 'var(--text-base)',
          lineHeight: 'var(--leading-body)',
          marginTop: 'var(--space-5)',
        }}
      >
        {t(line ? 'lineComplete.expiry' : 'googleComplete.expiry')}
      </p>
    </main>
  );
}
