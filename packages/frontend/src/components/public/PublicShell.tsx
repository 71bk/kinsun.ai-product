'use client';

import type { ReactNode } from 'react';
import { LocaleProvider, useLocale } from '@/lib/i18n/locale-context';
import { localeTag, type Locale } from '@/lib/i18n/messages';
import { PublicFooter } from './PublicFooter';
import { PublicHeader } from './PublicHeader';
import { SkipLink } from './SkipLink';
import styles from './PublicShell.module.css';

export interface PublicShellProps {
  initialLocale: Locale;
  /** Whether a session cookie is present, decided by the (server) caller —
   *  same contract as SurfaceShell's `signedIn`: it only picks the header CTA,
   *  never an authorization signal. */
  signedIn: boolean;
  /** Lets a product-led public page own its header/footer while retaining the
   *  locale provider, skip link, and public surface token scope. */
  immersive?: boolean;
  children: ReactNode;
}

/** Shell for the public surface (MASTER.md §3, §7.3): the signed-out landing
 *  page and the legal pages under `app/(public)/`. */
export function PublicShell({ initialLocale, signedIn, immersive = false, children }: PublicShellProps) {
  return (
    <LocaleProvider initialLocale={initialLocale}>
      <PublicFrame signedIn={signedIn} immersive={immersive}>
        {children}
      </PublicFrame>
    </LocaleProvider>
  );
}

function PublicFrame({
  signedIn,
  immersive,
  children,
}: {
  signedIn: boolean;
  immersive: boolean;
  children: ReactNode;
}) {
  const { locale } = useLocale();

  return (
    <div className={styles.shell} data-surface="public" lang={localeTag(locale)}>
      <SkipLink />
      {immersive ? null : <PublicHeader signedIn={signedIn} />}
      <main
        id="main-content"
        className={`${styles.main} ${immersive ? styles.immersiveMain : ''}`}
      >
        {children}
      </main>
      {immersive ? null : <PublicFooter />}
    </div>
  );
}
