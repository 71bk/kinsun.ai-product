'use client';

import { Check } from '@phosphor-icons/react';
import type { ReactNode } from 'react';
import styles from './FilterChip.module.css';

export interface FilterChipProps {
  children: ReactNode;
  selected: boolean;
  onClick: () => void;
  count?: number;
  disabled?: boolean;
}

export function FilterChip({ children, selected, onClick, count, disabled }: FilterChipProps) {
  return (
    <button
      aria-pressed={selected}
      className={styles.chip}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <span className={styles.check} data-visible={selected} aria-hidden="true">
        <Check size={16} weight="bold" />
      </span>
      <span>{children}</span>
      {typeof count === 'number' && <span className={styles.count}>{count}</span>}
    </button>
  );
}
