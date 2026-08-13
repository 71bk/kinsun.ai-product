'use client';

import type { SpeechLanguage } from '@/lib/voice/speech-gateway-client';
import styles from './LanguageSelect.module.css';

export interface LanguageOption {
  language: SpeechLanguage;
  label: string;
  /** Stated plainly when the reply cannot be spoken back in this language. */
  replyIsTextOnly: boolean;
}

export const LANGUAGE_OPTIONS: readonly LanguageOption[] = [
  { language: 'zh-TW', label: '國語', replyIsTextOnly: false },
  { language: 'nan-TW', label: '台語', replyIsTextOnly: true },
  { language: 'hak-TW', label: '客語', replyIsTextOnly: true },
  { language: 'en-US', label: 'English', replyIsTextOnly: false },
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
 *
 * Where the reply cannot be spoken back, the option says so up front instead of
 * letting the elder discover the silence after speaking.
 */
export function LanguageSelect({ language, onChange, disabled }: LanguageSelectProps) {
  const selected = LANGUAGE_OPTIONS.find((option) => option.language === language);

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

      {selected?.replyIsTextOnly === true && (
        <p className={styles.hint}>
          {selected.label}目前可以聽懂您說的話，回答會用文字顯示，還沒辦法唸出來。
        </p>
      )}
    </div>
  );
}
