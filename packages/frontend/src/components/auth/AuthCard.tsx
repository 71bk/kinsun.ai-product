'use client';

import { Sun } from '@phosphor-icons/react';
import type { ReactNode } from 'react';
import styles from './AuthCard.module.css';

export interface AuthCardProps {
  eyebrow: string;
  title: string;
  subtitle?: string;
  heroHeadline: string;
  heroPoints: ReactNode;
  children: ReactNode;
}

/** Compact card version of the sign-in hero + form pairing — see AuthCard.module.css. */
export function AuthCard({ eyebrow, title, subtitle, heroHeadline, heroPoints, children }: AuthCardProps) {
  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.hero}>
          <span aria-hidden="true" className={styles.heroIcon}>
            <Sun size={22} weight="fill" />
          </span>
          <div>
            <p className={styles.heroHeadline}>{heroHeadline}</p>
            <ul className={styles.heroPoints}>{heroPoints}</ul>
          </div>
        </div>
        <div className={styles.formArea}>
          <span className={styles.eyebrow}>{eyebrow}</span>
          <h1 className={styles.title}>{title}</h1>
          {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          {children}
        </div>
      </div>
    </div>
  );
}
