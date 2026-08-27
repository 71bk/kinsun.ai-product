'use client';

import { AuthSubmitButton } from '@/components/AuthSubmitButton';
import { AuthCard } from '@/components/auth/AuthCard';
import { AuthDivider } from '@/components/auth/AuthDivider';
import { AuthField } from '@/components/auth/AuthField';
import { ForgotPasswordHint } from '@/components/auth/ForgotPasswordHint';
import { LineContinueButton } from '@/components/auth/OAuthButtons';
import { TrustPoint } from '@/components/auth/TrustPoint';
import { touchLinkStyle } from '@/components/touch-link';
import { useLocale } from '@/lib/i18n/locale-context';

export function StaffSignInView({
  nativeEnabled,
  showLine,
}: {
  nativeEnabled: boolean;
  showLine: boolean;
}) {
  const { t } = useLocale();

  return (
    <AuthCard
      eyebrow={t('authLayout.welcomeBack')}
      heroHeadline={t('staffSignIn.heroHeadline')}
      heroPoints={
        <>
          <TrustPoint>{t('staffSignIn.heroPoint1')}</TrustPoint>
          <TrustPoint>{t('staffSignIn.heroPoint2')}</TrustPoint>
        </>
      }
      subtitle={t('staffSignIn.subtitle')}
      title={t('staffSignIn.title')}
    >
      <p
        style={{
          color: 'var(--color-muted-foreground)',
          lineHeight: 'var(--leading-body)',
          margin: 'var(--space-4) 0 0',
        }}
      >
        {t('staffSignIn.body')}
      </p>

      <form
        action={nativeEnabled ? '/backend/auth/kinsun/login' : '/backend/auth/login'}
        method="post"
        style={{ marginTop: 'var(--space-4)' }}
      >
        {!nativeEnabled && <input name="intent" type="hidden" value="STAFF" />}
        {!nativeEnabled && <input name="provider" type="hidden" value="GOOGLE" />}
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        {nativeEnabled && (
          <>
            <AuthField
              autoComplete="email"
              label={t('common.email')}
              maxLength={254}
              name="email"
              placeholder="name@organization.example"
              required
              type="email"
            />
            <AuthField
              autoComplete="current-password"
              hidePasswordLabel={t('authLayout.hidePassword')}
              label={t('common.password')}
              labelSuffix={
                <ForgotPasswordHint
                  hint={t('authLayout.forgotPasswordHint')}
                  label={t('authLayout.forgotPassword')}
                />
              }
              maxLength={128}
              minLength={12}
              name="password"
              required
              showPasswordLabel={t('authLayout.showPassword')}
              type="password"
            />
          </>
        )}
        <div style={{ marginTop: 'var(--space-6)' }}>
          <AuthSubmitButton>
            {nativeEnabled ? t('authLayout.signIn') : t('common.continueWithGoogle')}
          </AuthSubmitButton>
        </div>
      </form>

      {showLine && (
        <>
          <AuthDivider label={t('authLayout.divider')} />
          <form action="/backend/auth/login" method="post">
            <input name="intent" type="hidden" value="STAFF" />
            <input name="provider" type="hidden" value="LINE" />
            <input name="returnTo" type="hidden" value="/onboarding/resolve" />
            <LineContinueButton label={t('staffSignIn.lineButton')} />
          </form>
          <p
            style={{
              color: 'var(--color-muted-foreground)',
              fontSize: 'var(--text-sm)',
              marginTop: 'var(--space-3)',
              textAlign: 'center',
            }}
          >
            {t('staffSignIn.lineHint')}
          </p>
        </>
      )}

      <p style={{ color: 'var(--color-muted-foreground)', marginTop: 'var(--space-6)', textAlign: 'center' }}>
        {t('staffSignIn.notActivated')}
      </p>
      <p
        style={{
          color: 'var(--color-muted-foreground)',
          fontSize: 'var(--text-sm)',
          marginTop: 'var(--space-2)',
          textAlign: 'center',
        }}
      >
        工作人員帳號由機構建立，不開放自行註冊。Staff accounts are organization-provisioned.
      </p>

      <p
        style={{
          color: 'var(--color-muted-foreground)',
          fontSize: 'var(--text-sm)',
          marginTop: 'var(--space-4)',
          textAlign: 'center',
        }}
      >
        <a href="/privacy" style={{ ...touchLinkStyle, color: 'inherit' }}>
          {t('public.nav.privacy')}
        </a>
        {' · '}
        <a href="/terms" style={{ ...touchLinkStyle, color: 'inherit' }}>
          {t('public.nav.terms')}
        </a>
      </p>
    </AuthCard>
  );
}
