'use client';

import { useState } from 'react';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import type { CareEventDecision, EventView } from '@/lib/api/events';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './EventReviewControls.module.css';

const DECISIONS: CareEventDecision[] = ['VERIFY', 'CORRECT', 'REJECT', 'EXCLUDE'];

export interface EventReviewControlsProps {
  event: EventView;
  onReview: (
    event: EventView,
    decision: CareEventDecision,
    correctedContent?: string,
  ) => Promise<void>;
}

export function EventReviewControls({ event, onReview }: EventReviewControlsProps) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [draftContent, setDraftContent] = useState(event.content);
  const [decision, setDecision] = useState<CareEventDecision>('VERIFY');
  const [saving, setSaving] = useState(false);
  const reviewable = event.status === 'CANDIDATE' || event.status === 'NEEDS_REVIEW';

  if (!reviewable) return null;

  async function submit() {
    setSaving(true);
    try {
      await onReview(event, decision, decision === 'CORRECT' ? draftContent : undefined);
      setOpen(false);
      setConfirming(false);
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <button className={styles.reviewButton} onClick={() => setOpen(true)} type="button">
        {t('eventTable.review')}
      </button>
    );
  }

  return (
    <div className={styles.controls}>
      <label className={styles.label}>
        <span>{t('eventTable.decision')}</span>
        <select
          className={styles.select}
          disabled={saving}
          onChange={(changeEvent) =>
            setDecision(changeEvent.currentTarget.value as CareEventDecision)
          }
          value={decision}
        >
          {DECISIONS.map((item) => (
            <option key={item} value={item}>
              {t(`decision.${item}` as MessageKey)}
            </option>
          ))}
        </select>
      </label>
      {decision === 'CORRECT' && (
        <label className={styles.label}>
          <span>{t('eventTable.correctedContent')}</span>
          <textarea
            className={styles.textarea}
            disabled={saving}
            onChange={(changeEvent) => setDraftContent(changeEvent.currentTarget.value)}
            rows={4}
            value={draftContent}
          />
        </label>
      )}
      <div className={styles.actions}>
        <button
          className={styles.cancelButton}
          disabled={saving}
          onClick={() => setOpen(false)}
          type="button"
        >
          {t('eventTable.cancel')}
        </button>
        <button
          className={styles.submitButton}
          disabled={saving || (decision === 'CORRECT' && !draftContent.trim())}
          onClick={() => setConfirming(true)}
          type="button"
        >
          {t('eventTable.submit')}
        </button>
      </div>
      <ConfirmationDialog
        busy={saving}
        confirmLabel={t('eventTable.submit')}
        description={t('eventTable.confirmDescription')}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void submit()}
        open={confirming}
        title={t('eventTable.confirmTitle')}
        tone={decision === 'REJECT' || decision === 'EXCLUDE' ? 'destructive' : 'default'}
      />
    </div>
  );
}
