'use client';

import { useEffect } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import { ErrorState } from './ErrorState';
import styles from './RouteErrorBoundary.module.css';

export interface RouteErrorBoundaryProps {
  error: Error & { digest?: string };
  reset: () => void;
  /** Distinguishes the surface in the console line only — never shown. */
  scope: string;
}

/**
 * Shared body for the care and family route boundaries.
 *
 * Both surfaces need exactly the same discipline, and it is the kind that
 * erodes if each boundary restates it:
 *
 *  - The error is never rendered. On the family surface this component is what
 *    a `FamilyDataRedlineError` becomes, and its message names the restricted
 *    field Core sent. MASTER.md §11 requires that a withheld report leave no
 *    trace on screen — telling the reader a transcript arrived is exactly the
 *    disclosure the redline exists to prevent. §10.2 applies the same rule to
 *    the care surface's permission-denied state.
 *  - The copy says only that the page is unavailable, so it cannot accidentally
 *    become a channel for whatever the throw site knew.
 *  - `reset()` is offered because most throws here are transport failures, and
 *    §8's error-recovery rule wants a way forward rather than a dead end.
 *
 * Both surfaces sit inside a `LocaleProvider` (SurfaceShell), so `ErrorState`
 * and `useLocale` are safe here. The root boundary is not, and deliberately
 * does not use this component.
 */
export function RouteErrorBoundary({ error, reset, scope }: RouteErrorBoundaryProps) {
  const { t } = useLocale();

  useEffect(() => {
    /* Name and digest only — the message is the thing we just refused to put
       on screen, so it does not belong in a log either (AGENTS.md §4). */
    console.error('[route-error]', { scope, name: error.name, digest: error.digest });
  }, [error, scope]);

  return (
    <main className={styles.page}>
      <ErrorState
        action={
          <button className={styles.retryButton} onClick={reset} type="button">
            {t('common.retry')}
          </button>
        }
        description={t('error.routeBoundary')}
      />
    </main>
  );
}
