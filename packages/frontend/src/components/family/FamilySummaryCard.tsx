import type { ReactNode } from 'react';
import styles from './FamilySummaryCard.module.css';

export interface FamilySummaryCardProps {
  title: ReactNode;
  children: ReactNode;
}

/**
 * A titled block on the family home page — today's report, this week's
 * overview, recent important events. Gives the three sections one consistent
 * card shape instead of three hand-rolled `<section>` blocks.
 */
export function FamilySummaryCard({ title, children }: FamilySummaryCardProps) {
  return (
    <section className={styles.card}>
      <h2 className={styles.title}>{title}</h2>
      <div className={styles.body}>{children}</div>
    </section>
  );
}
