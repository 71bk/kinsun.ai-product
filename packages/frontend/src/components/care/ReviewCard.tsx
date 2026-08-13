'use client';

import { EvidenceBlock } from '@/components/care/EvidenceBlock';
import { EventReviewControls } from '@/components/care/EventReviewControls';
import { careEventState, StateCard } from '@/components/StateCard';
import type { CareEventDecision, EventView } from '@/lib/api/events';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './ReviewCard.module.css';

export interface ReviewCardProps {
  event: EventView;
  onReview: (
    event: EventView,
    decision: CareEventDecision,
    correctedContent?: string,
  ) => Promise<void>;
}

export function ReviewCard({ event, onReview }: ReviewCardProps) {
  const { t } = useLocale();

  return (
    <StateCard
      actions={<EventReviewControls event={event} onReview={onReview} />}
      meta={
        <EvidenceBlock
          consentVersion={event.consentVersion}
          sourceCount={event.evidenceRefs.length}
          version={event.version}
        />
      }
      state={careEventState(event.status)}
      stateLabel={t(`eventStatus.${event.status}` as MessageKey)}
      title={t(`eventType.${event.eventType}` as MessageKey)}
    >
      <div className={styles.content}>{event.content}</div>
      <dl className={styles.meta}>
        <div>
          <dt>{t('eventTable.colDate')}</dt>
          <dd>{event.eventDate}</dd>
        </div>
        <div>
          <dt>{t('eventTable.colConfidence')}</dt>
          <dd>{t(`confidence.${event.confidenceBand}` as MessageKey)}</dd>
        </div>
      </dl>
    </StateCard>
  );
}
