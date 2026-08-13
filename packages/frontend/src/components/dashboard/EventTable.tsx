'use client';

import { EvidenceBlock } from '@/components/care/EvidenceBlock';
import { EventReviewControls } from '@/components/care/EventReviewControls';
import { ReviewCard } from '@/components/care/ReviewCard';
import { careEventState, StateBadge } from '@/components/StateCard';
import { EmptyState } from '@/components/ui/EmptyState';
import type { CareEventDecision, EventView } from '@/lib/api/events';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './EventTable.module.css';

export interface EventTableProps {
  events: EventView[];
  onReview: (
    event: EventView,
    decision: CareEventDecision,
    correctedContent?: string,
  ) => Promise<void>;
}

export function EventTable({ events, onReview }: EventTableProps) {
  const { t } = useLocale();

  if (events.length === 0) {
    return <EmptyState description={t('eventTable.empty')} title={t('eventTable.emptyTitle')} />;
  }

  return (
    <section aria-label={t('eventTable.caption')} className={styles.region}>
      <table className={styles.table}>
        <caption className={styles.srOnly}>{t('eventTable.caption')}</caption>
        <thead>
          <tr>
            <th>{t('eventTable.colDate')}</th>
            <th>{t('eventTable.colType')}</th>
            <th>{t('eventTable.colContent')}</th>
            <th>{t('eventTable.colConfidence')}</th>
            <th>{t('eventTable.colStatus')}</th>
            <th>{t('eventTable.colEvidence')}</th>
            <th>{t('eventTable.colActions')}</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.eventId}>
              <td className={styles.nowrap}>{event.eventDate}</td>
              <td>{t(`eventType.${event.eventType}` as MessageKey)}</td>
              <td className={styles.content}>{event.content}</td>
              <td>{t(`confidence.${event.confidenceBand}` as MessageKey)}</td>
              <td>
                <StateBadge
                  label={t(`eventStatus.${event.status}` as MessageKey)}
                  state={careEventState(event.status)}
                />
              </td>
              <td>
                <EvidenceBlock
                  compact
                  consentVersion={event.consentVersion}
                  sourceCount={event.evidenceRefs.length}
                  version={event.version}
                />
              </td>
              <td>
                <EventReviewControls event={event} onReview={onReview} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={styles.cards}>
        {events.map((event) => (
          <ReviewCard event={event} key={event.eventId} onReview={onReview} />
        ))}
      </div>
    </section>
  );
}
