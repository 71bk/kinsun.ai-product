'use client';

import type { SpeechLanguage } from '@/lib/voice/speech-gateway-client';
import styles from './LanguageSelect.module.css';

export interface LanguageOption {
  language: SpeechLanguage;
  label: string;
}

// Keep Taiwanese and Hakka out of the elder-facing selector until their speech
// providers have been deployed and validated. Backend language routes remain intact.
export const LANGUAGE_OPTIONS: readonly LanguageOption[] = [
  { language: 'zh-TW', label: '國語' },
  { language: 'en-US', label: 'English' },
];

export interface LanguageSelectProps {
  language: SpeechLanguage;
  onChange: (language: SpeechLanguage) => void;
  /** Disabled mid-turn so the language cannot change under an in-flight utterance. */
  disabled?: boolean;
}

/**
 * Spoken-language selector.
 *
 * The language is chosen rather than detected because getting it wrong is not a
 * neutral error: transcribing Taiwanese with a Mandarin model returns fluent text
 * the elder never said, and that text would then be treated as what they said.
 */
export function LanguageSelect({ language, onChange, disabled }: LanguageSelectProps) {
  return (
    <div className={styles.wrapper}>
      <div aria-label="選擇您要說的語言" className={styles.group} role="radiogroup">
        {LANGUAGE_OPTIONS.map((option) => {
          const isSelected = option.language === language;
          return (
            <button
              key={option.language}
              type="button"
              role="radio"
              aria-checked={isSelected}
              className={styles.option}
              data-selected={isSelected}
              disabled={disabled}
              onClick={() => onChange(option.language)}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
