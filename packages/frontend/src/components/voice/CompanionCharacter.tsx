'use client';

import styles from './CompanionCharacter.module.css';

export type ConversationState = 'idle' | 'listening' | 'processing' | 'speaking' | 'sleeping';

interface CompanionCharacterProps {
  state: ConversationState;
  message?: string;
  characterName?: string;
}

export function CompanionCharacter({ state = 'idle', message, characterName = '小暖' }: CompanionCharacterProps) {
  return (
    <div className={styles.container}>
      {/* Character image with state-based animation */}
      <div className={`${styles.characterWrapper} ${styles[state]}`}>
        {/* Glow effect behind character */}
        <div className={styles.glow} />

        {/* Main character image */}
        <div className={styles.character}>
          {/* Plain <img>, not next/image — this is a bundled local asset, and
              the optimizer's default sandbox CSP on /_next/image responses
              isn't worth the tradeoff for a fixed 280x280 static PNG. */}
          <img src="/mascot.png" alt={characterName} width={280} height={280} className={styles.characterImage} />
        </div>

        {/* State indicators */}
        {state === 'processing' && (
          <div className={styles.thinkingBubble}>
            <span className={styles.dot}>●</span>
            <span className={styles.dot}>●</span>
            <span className={styles.dot}>●</span>
          </div>
        )}

        {state === 'sleeping' && (
          <div className={styles.sleepBubble}>
            <span className={styles.zzz}>Z</span>
            <span className={styles.zzz}>z</span>
            <span className={styles.zzz}>z</span>
          </div>
        )}
      </div>

      {/* Speech bubble */}
      {message && state !== 'sleeping' && (
        <div className={styles.speechBubble}>
          <p className={styles.messageText}>{message}</p>
        </div>
      )}

      {/* Character name tag */}
      <div className={styles.nameTag}>{characterName}</div>
    </div>
  );
}
