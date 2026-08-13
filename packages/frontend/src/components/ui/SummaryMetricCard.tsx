import type { ReactNode } from 'react';
import styles from './SummaryMetricCard.module.css';

export interface SummaryMetricCardProps {
  label: ReactNode;
  value: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
}

/**
 * A neutral count or workflow summary. There is intentionally no severity,
 * trend, score, or red/amber/green prop: those variants would make it too easy
 * to turn incomplete care data into a health assessment.
 */
export function SummaryMetricCard({ label, value, description, icon }: SummaryMetricCardProps) {
  return (
    <dl className={styles.card}>
      <dt className={styles.heading}>
        {icon && (
          <span className={styles.icon} aria-hidden="true">
            {icon}
          </span>
        )}
        <span className={styles.label}>{label}</span>
      </dt>
      <dd className={styles.value}>{value}</dd>
      {description && <dd className={styles.description}>{description}</dd>}
    </dl>
  );
}
