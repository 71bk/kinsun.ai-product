'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { AdminEntryLink } from '@/components/AdminEntryLink';
import { LanguageSwitch } from '@/components/LanguageSwitch';
import { SignOutButton } from '@/components/SignOutButton';
import { LocaleProvider, useLocale } from '@/lib/i18n/locale-context';
import { localeTag, type Locale } from '@/lib/i18n/messages';
import styles from './SurfaceShell.module.css';

type SurfaceName = 'care' | 'family' | 'admin';

const SURFACE_LABEL = {
  care: 'surface.careLabel',
  family: 'surface.familyLabel',
  admin: 'surface.adminLabel',
} as const;

export interface SurfaceShellProps {
  /** Selects the token overrides in `app/tokens.css`. The voice surface does not
   *  use this shell — it sets `data-surface` itself and has no language switch. */
  surface: SurfaceName;
  initialLocale: Locale;
  /**
   * Whether a session cookie is present, decided by the (server) layout.
   *
   * Only controls whether a sign-out affordance is offered — it is not an
   * authorization signal and must never gate content. The cookie's presence says
   * nothing about its validity; Core re-authorizes every read regardless
   * (AGENTS.md §5). Without it the shell would offer "sign out" on the sign-in
   * pages, which also live on these surfaces.
   */
  signedIn: boolean;
  children: ReactNode;
}

export function SurfaceShell({ surface, initialLocale, signedIn, children }: SurfaceShellProps) {
  return (
    <LocaleProvider initialLocale={initialLocale}>
      <SurfaceFrame surface={surface} signedIn={signedIn}>
        {children}
      </SurfaceFrame>
    </LocaleProvider>
  );
}

function SurfaceFrame({
  surface,
  signedIn,
  children,
}: {
  surface: SurfaceName;
  signedIn: boolean;
  children: ReactNode;
}) {
  const { locale, t } = useLocale();
  const pathname = usePathname();

  return (
    // `lang` is set here rather than on <html>: the root layout is shared with
    // the Chinese-only voice surface, so the switch must scope to this subtree.
    <div className={styles.shell} data-surface={surface} lang={localeTag(locale)}>
      <a className={styles.skipLink} href="#surface-main-content">
        {t('common.skipToContent')}
      </a>
      <header className={styles.header}>
        {/* Only the admin console gets a clickable label. It is the one surface
            whose own screens replace the page wholesale — the issue form and the
            one-time credential panel both take over — so the chrome has to carry
            the way back to the ledger. Care and family keep their own in-page
            navigation and do not need a second one. */}
        {surface === 'admin' ? (
          <Link
            aria-current={pathname === '/admin' ? 'page' : undefined}
            className={styles.surfaceHome}
            href="/admin"
          >
            {t(SURFACE_LABEL[surface])}
          </Link>
        ) : (
          <span className={styles.surfaceLabel}>{t(SURFACE_LABEL[surface])}</span>
        )}
        <div className={styles.utilities}>
          {/* Care only. An administrator holds a tenant-level membership with no
              care unit, so they never reach the family surface, and offering the
              console to a family member would cost a `/api/v1/me` round trip on
              every page to answer a question whose answer is always no. */}
          {signedIn && surface === 'care' && <AdminEntryLink />}
          <LanguageSwitch />
          {signedIn && <SignOutButton label={t('common.signOut')} />}
        </div>
      </header>
      <div className={styles.content} id="surface-main-content" tabIndex={-1}>
        {children}
      </div>
    </div>
  );
}
