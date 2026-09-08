import Link from 'next/link';
import { cookies } from 'next/headers';
import { ClearBrowserSessionState } from '@/components/ClearBrowserSessionState';
import { browserAuthCookieNames } from '@/lib/server/app-session-cookie';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { translate, type MessageKey } from '@/lib/i18n/messages';

/* The role chooser is the one page whose audience is unknown — an elder, a
   family member and a care worker all land here before anything is known about
   them. It therefore renders at the elder scale (inherited from <body>): too
   large for a care worker costs nothing, too small for a 75+ user costs them
   the page (MASTER.md §5.1). Each card is a full 64px-plus target per §6.1. */
const cardStyle = {
  /* The border is this card's only affordance boundary, so WCAG 1.4.11 / §13's
     3:1 for UI components applies to it. --color-border-strong is 1.45:1 on
     white, which is decoration, not a boundary — --color-primary is 3.68:1. */
  border: '2px solid var(--color-primary)',
  borderRadius: 'var(--radius-md)',
  color: 'inherit',
  display: 'block',
  minHeight: 'var(--touch-min)',
  padding: 'var(--space-5)',
  textDecoration: 'none',
};

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const [{ error }, cookieStore] = await Promise.all([searchParams, cookies()]);
  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  const t = (key: MessageKey) => translate(locale, key);
  const sessionCookiePresent = browserAuthCookieNames().some((name) =>
    Boolean(cookieStore.get(name)?.value),
  );
  return (
    <main style={{ margin: '0 auto', maxWidth: 680, padding: 'var(--space-6)' }}>
      {/* Cookie presence is only a cleanup guard, never authorization. When a
          session cookie remains (for example after a failed re-auth), preserve
          its browser selection instead of creating a half-signed-in state. */}
      {!sessionCookiePresent && <ClearBrowserSessionState />}
      <h1 style={{ fontSize: 'var(--text-2xl)', marginBottom: 'var(--space-2)' }}>
        {t('signInChooser.title')}
      </h1>
      <p
        style={{
          color: 'var(--color-foreground)',
          fontSize: 'var(--text-base)',
          lineHeight: 'var(--leading-body)',
          marginBottom: 'var(--space-6)',
        }}
      >
        {t('signInChooser.description')}
      </p>
      {error && (
        <p
          role="alert"
          style={{ color: 'var(--color-destructive)', marginBottom: 'var(--space-4)' }}
        >
          {t('signInChooser.error')}
        </p>
      )}
      <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <Link href="/elder/start" style={cardStyle}>
          <strong style={{ fontSize: 'var(--text-lg)' }}>{t('signInChooser.elder')}</strong>
          <p style={{ marginBottom: 0 }}>{t('signInChooser.elderDescription')}</p>
        </Link>
        <Link href="/family/join" style={cardStyle}>
          <strong style={{ fontSize: 'var(--text-lg)' }}>{t('signInChooser.family')}</strong>
          <p style={{ marginBottom: 0 }}>{t('signInChooser.familyDescription')}</p>
        </Link>
        <Link href="/staff/sign-in" style={cardStyle}>
          <strong style={{ fontSize: 'var(--text-lg)' }}>{t('signInChooser.staff')}</strong>
          <p style={{ marginBottom: 0 }}>{t('signInChooser.staffDescription')}</p>
        </Link>
      </div>
    </main>
  );
}
