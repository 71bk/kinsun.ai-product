'use client';

import { Files, ShieldCheck } from '@phosphor-icons/react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './EvidenceBlock.module.css';

export interface EvidenceBlockProps {
  sourceCount: number;
  version: number;
  consentVersion?: number;
  compact?: boolean;
}

/**
 * Evidence metadata without exposing opaque reference values or reconstructing
 * transcripts. The API only promises references, so the UI only states count.
 */
export function EvidenceBlock({
  sourceCount,
  version,
  consentVersion,
  compact = false,
}: EvidenceBlockProps) {
  const { t } = useLocale();

  return (
    <dl className={styles.block} data-compact={compact}>
      <div className={styles.item}>
        <dt>
          <Files size={18} weight="bold" aria-hidden="true" />
          <span>{t('evidence.sources')}</span>
        </dt>
        <dd>{sourceCount}</dd>
      </div>
      <div className={styles.item}>
        <dt>
          <ShieldCheck size={18} weight="bold" aria-hidden="true" />
          <span>{t('evidence.version')}</span>
        </dt>
        <dd>{version}</dd>
      </div>
      {typeof consentVersion === 'number' && (
        <div className={styles.item}>
          <dt>{t('evidence.consentVersion')}</dt>
          <dd>{consentVersion}</dd>
        </div>
      )}
    </dl>
  );
}
