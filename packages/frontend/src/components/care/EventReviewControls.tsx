'use client';

import { useId, useState } from 'react';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import type {
  CareEventDecision,
  CoreCareEventType,
  EventCorrection,
  EventView,
} from '@/lib/api/events';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './EventReviewControls.module.css';

const DECISIONS: CareEventDecision[] = ['VERIFY', 'CORRECT', 'REJECT', 'EXCLUDE'];
const EVENT_TYPES: CoreCareEventType[] = [
  'MEAL',
  'ACTIVITY',
  'SLEEP',
  'MEDICATION_STATEMENT',
  'EMOTION_EXPRESSION',
  'SOCIAL_CONTACT',
  'EXPECTED_CONTACT_MISSED',
  'ACTIVITY_PARTICIPATION',
  'ACTIVITY_CANCELLED',
  'COMPANIONSHIP_NEED',
];

/** ISO timestamp → the local "YYYY-MM-DDTHH:mm" a datetime-local input expects. */
function toLocalInput(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export interface EventReviewControlsProps {
  event: EventView;
  onReview: (
    event: EventView,
    decision: CareEventDecision,
    correction?: EventCorrection,
  ) => Promise<void>;
}

export function EventReviewControls({ event, onReview }: EventReviewControlsProps) {
  const { t } = useLocale();
  const clearId = useId();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [draftContent, setDraftContent] = useState(event.content);
  const [draftType, setDraftType] = useState<CoreCareEventType>(event.eventType);
  const [draftTime, setDraftTime] = useState(() => toLocalInput(event.eventTime));
  const [clearTime, setClearTime] = useState(false);
  const [decision, setDecision] = useState<CareEventDecision>('VERIFY');
  const [saving, setSaving] = useState(false);
  const reviewable = event.status === 'CANDIDATE' || event.status === 'NEEDS_REVIEW';

  if (!reviewable) return null;

  /* B03: type and time ride along with the corrected content. An unchanged
     time is left undefined so the client omits it; "clear" sends null; a new
     value is sent as UTC so the timezone is explicit. */
  function correction(): EventCorrection {
    let eventTime: EventCorrection['eventTime'];
    if (clearTime) eventTime = event.eventTime === null ? undefined : null;
    else if (draftTime && draftTime !== toLocalInput(event.eventTime)) {
      eventTime = new Date(draftTime).toISOString();
    }
    return { content: draftContent, eventType: draftType, eventTime };
  }

  async function submit() {
    setSaving(true);
    try {
      await onReview(event, decision, decision === 'CORRECT' ? correction() : undefined);
      setOpen(false);
    } catch {
      // The page owns the visible error (permission loss unmounts this control,
      // a version conflict shows the reload notice). Keep the form open so the
      // reviewer's draft survives, but do not leak an unhandled rejection.
    } finally {
      setConfirming(false);
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
        <>
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
          <label className={styles.label}>
            <span>{t('eventTable.correctedType')}</span>
            <select
              className={styles.select}
              disabled={saving}
              onChange={(changeEvent) =>
                setDraftType(changeEvent.currentTarget.value as CoreCareEventType)
              }
              value={draftType}
            >
              {EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {t(`eventType.${type}` as MessageKey)}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.label}>
            <span>{t('eventTable.correctedTime')}</span>
            <input
              className={styles.input}
              disabled={saving || clearTime}
              onChange={(changeEvent) => setDraftTime(changeEvent.currentTarget.value)}
              type="datetime-local"
              value={clearTime ? '' : draftTime}
            />
          </label>
          <div className={styles.checkRow}>
            <input
              checked={clearTime}
              disabled={saving}
              id={clearId}
              onChange={(changeEvent) => setClearTime(changeEvent.currentTarget.checked)}
              type="checkbox"
            />
            <label htmlFor={clearId}>{t('eventTable.clearTime')}</label>
          </div>
        </>
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
