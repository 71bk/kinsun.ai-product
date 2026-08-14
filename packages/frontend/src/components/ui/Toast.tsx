'use client';

import { CheckCircle, X } from '@phosphor-icons/react';
import { useEffect, type ReactNode } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './Toast.module.css';

export interface ToastProps {
  message: ReactNode;
  onDismiss: () => void;
  /** Auto-dismiss delay in ms; 3000-5000 is the accessible range. */
  durationMs?: number;
}

/**
 * Confirms a write action completed. Unlike `ConfirmationDialog`, this is
 * non-blocking and never takes focus — a routine success must not interrupt a
 * screen reader user the way `ErrorState`'s `role="alert"` deliberately does.
 */
export function Toast({ message, onDismiss, durationMs = 4000 }: ToastProps) {
  const { t } = useLocale();

  useEffect(() => {
    const timer = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(timer);
  }, [durationMs, onDismiss]);

  return (
    <div aria-live="polite" className={styles.toast} role="status">
      <CheckCircle aria-hidden="true" className={styles.icon} size={22} weight="bold" />
      <span className={styles.message}>{message}</span>
      <button
        aria-label={t('common.dismiss')}
        className={styles.dismiss}
        onClick={onDismiss}
        type="button"
      >
        <X aria-hidden="true" size={18} weight="bold" />
      </button>
    </div>
  );
}
