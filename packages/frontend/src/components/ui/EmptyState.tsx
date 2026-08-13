'use client';

import { Tray } from '@phosphor-icons/react';
import { useId, type ReactNode } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './EmptyState.module.css';

export interface EmptyStateProps {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}

/** A first-class no-data state, distinct from loading and failure. */
export function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  const { t } = useLocale();
  const titleId = useId();

  return (
    <section aria-labelledby={titleId} className={styles.state} role="status">
      <div className={styles.icon} aria-hidden="true">
        {icon ?? <Tray size={32} weight="bold" />}
      </div>
      <h2 className={styles.title} id={titleId}>
        {title ?? t('common.emptyTitle')}
      </h2>
      {description && <div className={styles.description}>{description}</div>}
      {action && <div className={styles.action}>{action}</div>}
    </section>
  );
}
