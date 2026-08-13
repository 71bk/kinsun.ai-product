'use client';

import { MagnifyingGlass, X } from '@phosphor-icons/react';
import { useId } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './SearchField.module.css';

export interface SearchFieldProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
  clearLabel?: string;
  name?: string;
  disabled?: boolean;
  hideLabel?: boolean;
}

export function SearchField({
  value,
  onChange,
  label,
  placeholder,
  clearLabel,
  name = 'search',
  disabled = false,
  hideLabel = false,
}: SearchFieldProps) {
  const { t } = useLocale();
  const id = useId();

  return (
    <div className={styles.field}>
      <label className={styles.label} data-visually-hidden={hideLabel} htmlFor={id}>
        {label ?? t('common.search')}
      </label>
      <div className={styles.control}>
        <MagnifyingGlass className={styles.searchIcon} size={20} weight="bold" aria-hidden="true" />
        <input
          autoComplete="off"
          className={styles.input}
          disabled={disabled}
          id={id}
          name={name}
          onChange={(event) => onChange(event.currentTarget.value)}
          placeholder={placeholder ?? t('common.searchPlaceholder')}
          type="search"
          value={value}
        />
        {value && (
          <button
            aria-label={clearLabel ?? t('common.clearSearch')}
            className={styles.clear}
            disabled={disabled}
            onClick={() => onChange('')}
            type="button"
          >
            <X size={20} weight="bold" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
