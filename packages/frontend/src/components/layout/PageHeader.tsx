import type { ReactNode } from 'react';
import styles from './PageHeader.module.css';

export interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}

/**
 * The single page-level heading used by care and family routes.
 *
 * It deliberately owns the h1 so individual screens do not invent competing
 * type scales or skip heading levels. Workflow state belongs in `meta`, not in
 * a colour treatment on the title.
 */
export function PageHeader({ title, description, eyebrow, meta, actions }: PageHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.layout}>
        <div className={styles.copy}>
          {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
          <h1 className={styles.title}>{title}</h1>
          {description && <div className={styles.description}>{description}</div>}
          {meta && <div className={styles.meta}>{meta}</div>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
    </header>
  );
}
