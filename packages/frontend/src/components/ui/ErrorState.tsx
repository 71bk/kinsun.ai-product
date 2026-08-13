'use client';

import { WarningCircle } from '@phosphor-icons/react';
import { useId, type ReactNode } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './ErrorState.module.css';

export interface ErrorStateProps {
  title?: ReactNode;
  description: ReactNode;
  action?: ReactNode;
}

/**
 * A recoverable system failure. Domain validation and permission denial should
 * pass their own precise, non-diagnostic copy rather than collapsing into this.
 */
export function ErrorState({ title, description, action }: ErrorStateProps) {
  const { t } = useLocale();
  const titleId = useId();

  return (
    <section aria-labelledby={titleId} className={styles.state} role="alert">
      <WarningCircle className={styles.icon} size={32} weight="bold" aria-hidden="true" />
      <h2 className={styles.title} id={titleId}>
        {title ?? t('common.errorTitle')}
      </h2>
      <div className={styles.description}>{description}</div>
      {action && <div className={styles.action}>{action}</div>}
    </section>
  );
}
