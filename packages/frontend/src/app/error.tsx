'use client';

import { ArrowClockwise, CloudWarning } from '@phosphor-icons/react';
import Link from 'next/link';
import { useEffect } from 'react';
import styles from './RouteFallback.module.css';

/**
 * Root error boundary — the last catch below the root layout.
 *
 * It covers the elder surface (/, /consent, /elder/*) plus the pages that sit
 * outside a surface layout (/sign-in, /account/*, /onboarding/*). The care and
 * family subtrees have their own boundaries so they can keep their shell,
 * locale and 資料紅線 copy.
 *
 * This one cannot use `ErrorState`: that component calls `useLocale()`, which
 * throws outside a `LocaleProvider`, and the root layout deliberately has none
 * (MASTER.md §5.2 — the voice surface is Chinese-only). An error page that
 * itself throws is worse than no error page.
 */
export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    /* Name and digest only. The message can carry whatever the throw site put
       in it, and on this surface that may include elder content — AGENTS.md §4
       keeps transcripts and prompts out of general logs. The digest is what
       correlates with the server log entry anyway. */
    console.error('[route-error]', { name: error.name, digest: error.digest });
  }, [error]);

  return (
    <main className={styles.page}>
      <CloudWarning aria-hidden="true" className={styles.icon} size={64} weight="fill" />
      {/* role="alert" so a screen reader announces the state change; the
          heading carries the message rather than colour alone (§13). */}
      <h1 className={styles.title} role="alert">
        我這邊出了一點狀況
      </h1>
      <p className={styles.body}>剛剛沒有順利完成，請再試一次。如果還是這樣，等一下再回來看看。</p>
      <div className={styles.actions}>
        <button className={styles.primary} onClick={reset} type="button">
          <ArrowClockwise aria-hidden="true" size={28} weight="bold" />
          再試一次
        </button>
        <Link className={styles.secondary} href="/">
          回到首頁
        </Link>
      </div>
    </main>
  );
}
