'use client';

import { ArrowClockwise } from '@phosphor-icons/react';
import { useEffect } from 'react';
import styles from './RouteFallback.module.css';
import './globals.css';

/**
 * Catches what `error.tsx` cannot: a throw inside the root layout itself.
 *
 * React replaces the whole document in that case, so this file has to supply
 * its own <html> and <body> — and its own stylesheet import, since the root
 * layout's is gone with it. globals.css pulls in tokens.css, so the surface
 * scale and colours still resolve.
 *
 * `data-surface="voice"` is repeated here for the same reason the root layout
 * sets it: without a surface the :root values apply, which are the 16px care
 * scale, and a crash page is the worst place to shrink text for a 75+ reader.
 *
 * No <Link> here — the router may be part of what failed, so a plain anchor
 * that forces a fresh document load is the more reliable escape.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[global-error]', { name: error.name, digest: error.digest });
  }, [error]);

  return (
    <html lang="zh-Hant-TW">
      <body data-surface="voice">
        <main className={styles.page}>
          <h1 className={styles.title} role="alert">
            我這邊出了一點狀況
          </h1>
          <p className={styles.body}>畫面沒有順利載入，請再試一次。</p>
          <div className={styles.actions}>
            <button className={styles.primary} onClick={reset} type="button">
              <ArrowClockwise aria-hidden="true" size={28} weight="bold" />
              再試一次
            </button>
            <a className={styles.secondary} href="/">
              回到首頁
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
