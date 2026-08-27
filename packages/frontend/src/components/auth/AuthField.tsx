'use client';

import { Eye, EyeSlash } from '@phosphor-icons/react';
import { useId, useState } from 'react';
import styles from './AuthField.module.css';

export interface AuthFieldProps {
  name: string;
  label: string;
  type?: 'email' | 'password' | 'text';
  autoComplete?: string;
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  placeholder?: string;
  /** Rendered inline with the label — used for the "forgot password?" hint. */
  labelSuffix?: React.ReactNode;
  showPasswordLabel?: string;
  hidePasswordLabel?: string;
}

/**
 * Shared email/text/password field for the three sign-in entry points
 * (elder/start, family/sign-in, staff/sign-in). Password fields get a
 * show/hide toggle; the border/sizing follows the same
 * `--color-interactive-border` + `--touch-min` pattern as `SearchField`.
 */
export function AuthField({
  name,
  label,
  type = 'text',
  autoComplete,
  required,
  minLength,
  maxLength,
  placeholder,
  labelSuffix,
  showPasswordLabel = 'Show password',
  hidePasswordLabel = 'Hide password',
}: AuthFieldProps) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  const isPassword = type === 'password';
  const resolvedType = isPassword ? (visible ? 'text' : 'password') : type;

  return (
    <div className={styles.field}>
      <div className={styles.labelRow}>
        <label className={styles.label} htmlFor={id}>
          {label}
        </label>
        {labelSuffix}
      </div>
      <div className={styles.control}>
        <input
          autoComplete={autoComplete}
          className={styles.input}
          id={id}
          maxLength={maxLength}
          minLength={minLength}
          name={name}
          placeholder={placeholder}
          required={required}
          type={resolvedType}
        />
        {isPassword && (
          <button
            aria-label={visible ? hidePasswordLabel : showPasswordLabel}
            aria-pressed={visible}
            className={styles.toggle}
            onClick={() => setVisible((current) => !current)}
            type="button"
          >
            {visible ? (
              <EyeSlash aria-hidden="true" size={22} />
            ) : (
              <Eye aria-hidden="true" size={22} />
            )}
          </button>
        )}
      </div>
    </div>
  );
}
