'use client';

import { MicrophoneSlash } from '@phosphor-icons/react';
import styles from './MicPermissionGuide.module.css';

export interface MicPermissionGuideProps {
  onRetry: () => void;
}

/**
 * Plain-language mic-permission guidance (A01.3, docs/design-system/MASTER.md §10.1
 * Permission Denied — 附白話步驟). Tokens only, no raw hex (§14). The retry
 * button here is deliberately `secondary` (outline): the record button is
 * already the one filled button on this screen (§8.1).
 */
export function MicPermissionGuide({ onRetry }: MicPermissionGuideProps) {
  return (
    <div className={styles.guide} role="alert">
      <MicrophoneSlash aria-hidden="true" className={styles.icon} size={40} weight="fill" />
      <p>要先讓我使用麥克風才能說話。</p>
      <p>請在畫面上方的提示，點一下「允許」。</p>
      <button className={styles.retry} onClick={onRetry} type="button">
        <MicrophoneSlash size={32} weight="fill" aria-hidden="true" />
        <span>再允許一次</span>
      </button>
    </div>
  );
}
