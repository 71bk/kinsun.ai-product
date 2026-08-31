import { Compass } from '@phosphor-icons/react/dist/ssr';
import Link from 'next/link';
import styles from './RouteFallback.module.css';

/**
 * Root 404.
 *
 * Without this file Next serves its own default page: unstyled, English, at
 * the browser's base scale and with no way back. For a product whose primary
 * user is 75+ and whose UI is Chinese-only on this surface (MASTER.md §5.2),
 * that is a dead end rather than a recoverable state.
 *
 * The copy follows §1 "不責怪使用者": the subject is the system, and none of
 * 錯誤 / 失敗 / 無效 appears. A wrong address is not the reader's mistake.
 */
export default function NotFound() {
  return (
    <main className={styles.page}>
      <Compass aria-hidden="true" className={styles.icon} size={64} weight="fill" />
      <h1 className={styles.title}>這個頁面我找不到</h1>
      <p className={styles.body}>可能是網址不完整，或這個頁面已經換了位置。</p>
      <div className={styles.actions}>
        <Link className={styles.primary} href="/">
          回到首頁
        </Link>
      </div>
    </main>
  );
}
