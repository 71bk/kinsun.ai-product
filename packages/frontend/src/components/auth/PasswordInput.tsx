'use client';

import { Eye, EyeSlash } from '@phosphor-icons/react';
import { useState, type CSSProperties } from 'react';
import styles from './PasswordInput.module.css';

export interface PasswordInputProps {
  name: string;
  id?: string;
  autoComplete?: string;
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  placeholder?: string;
  className?: string;
  style?: CSSProperties;
  /** For the family/staff fields, which label the input with aria-label. */
  ariaLabel?: string;
  showLabel?: string;
  hideLabel?: string;
}

/**
 * A password field with a show/hide control, styled by the caller.
 *
 * The three sign-in entry points had no way to reveal what was typed. That is
 * a problem everywhere (skill section 8, `password-toggle`) and most of all on
 * /elder/start, whose users are 75+ and typing a 12-character minimum into a
 * masked box on a tablet.
 *
 * `AuthField` already solves this, but it owns the field's border and layout,
 * and the three views each style their own — so adopting it would restyle
 * pages rather than fix one gap. This component only adds the control.
 *
 * The button is a real, named button at `--touch-min` (64px on the voice
 * surface, 48px on care/family per MASTER.md section 6.1), with `aria-pressed`
 * reflecting state, so it satisfies the visual QA audit rather than dodging it.
 */
export function PasswordInput({
  name,
  id,
  autoComplete,
  required,
  minLength,
  maxLength,
  placeholder,
  className,
  style,
  ariaLabel,
  showLabel = '顯示密碼',
  hideLabel = '隱藏密碼',
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false);

  return (
    <span className={styles.control}>
      <input
        aria-label={ariaLabel}
        autoComplete={autoComplete}
        className={className}
        id={id}
        maxLength={maxLength}
        minLength={minLength}
        name={name}
        placeholder={placeholder}
        required={required}
        style={style}
        type={visible ? 'text' : 'password'}
      />
      <button
        aria-label={visible ? hideLabel : showLabel}
        aria-pressed={visible}
        className={styles.toggle}
        onClick={() => setVisible((current) => !current)}
        type="button"
      >
        {visible ? <EyeSlash aria-hidden="true" size={22} /> : <Eye aria-hidden="true" size={22} />}
      </button>
    </span>
  );
}
