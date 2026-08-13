'use client';

import { Keyboard, Microphone } from '@phosphor-icons/react';
import styles from './InputModeToggle.module.css';

export type InputMode = 'voice' | 'text';

export interface InputModeToggleProps {
  mode: InputMode;
  onChange: (mode: InputMode) => void;
  /** Disabled mid-turn so switching cannot discard an utterance being processed. */
  disabled?: boolean;
}

const OPTIONS: { mode: InputMode; label: string; icon: typeof Microphone; hint: string }[] = [
  { mode: 'voice', label: '說話', icon: Microphone, hint: '用說話的方式和我聊天' },
  { mode: 'text', label: '打字', icon: Keyboard, hint: '用打字的方式和我聊天' },
];

/**
 * Voice/text input switch.
 *
 * Both options carry an icon and a word rather than an icon alone, and each is a
 * full-size target: a small control is the first thing to fail for someone with
 * reduced dexterity or eyesight, which is the population this surface is for.
 *
 * Implemented as a radiogroup so the current mode is announced as a selection
 * rather than as two unrelated buttons.
 */
export function InputModeToggle({ mode, onChange, disabled }: InputModeToggleProps) {
  return (
    <div aria-label="選擇和我聊天的方式" className={styles.group} role="radiogroup">
      {OPTIONS.map((option) => {
        const selected = mode === option.mode;
        const IconComponent = option.icon;
        return (
          <button
            key={option.mode}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={option.hint}
            className={styles.option}
            data-selected={selected}
            disabled={disabled}
            onClick={() => onChange(option.mode)}
          >
            <IconComponent size={28} weight={selected ? 'fill' : 'regular'} aria-hidden="true" />
            <span>{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
