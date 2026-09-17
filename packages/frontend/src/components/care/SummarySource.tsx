'use client';

import { useEffect, useId, useState } from 'react';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import { getSummarySourceEvent, type EventView } from '@/lib/api/events';
import { useLocale } from '@/lib/i18n/locale-context';
import { EvidenceBlock } from './EvidenceBlock';
import styles from './SummarySource.module.css';

export function SummarySource({ config, elderId, eventId, onAccessDenied }: {
  config: ApiConfig; elderId: string; eventId: string; onAccessDenied: () => void;
}) {
  const { t, formatDateTime } = useLocale();
  const [open, setOpen] = useState(false);
  const [event, setEvent] = useState<EventView | null>(null);
  const [failed, setFailed] = useState(false);
  const panelId = useId();

  useEffect(() => {
    let current = true;
    setEvent(null);
    setFailed(false);
    if (open) {
      void getSummarySourceEvent(config, elderId, eventId).then((value) => {
        if (current) setEvent(value);
      }).catch((error) => {
        if (!current) return;
        setFailed(true);
        if (error instanceof ApiRequestError && [401, 403, 404].includes(error.status)) {
          onAccessDenied();
        }
      });
    }
    return () => { current = false; };
  }, [config, elderId, eventId, onAccessDenied, open]);

  return <div className={styles.source}>
    <button type="button" className={styles.toggle} aria-expanded={open}
      aria-controls={panelId} onClick={() => setOpen((value) => !value)}>
      {t(open ? 'summarySource.hide' : 'summarySource.view', { id: eventId.slice(0, 8) })}
    </button>
    {open && <div id={panelId} className={styles.panel}>
      <p className={styles.notice}>{t('summarySource.currentNotice')}</p>
      {failed ? <p role="alert">{t('summarySource.unavailable')}</p> : !event ?
        <p role="status" aria-busy="true">{t('common.loading')}</p> : <>
          <p><strong>{t(`eventType.${event.eventType}`)}</strong> · {t(`eventStatus.${event.status}`)}</p>
          <p>{event.content}</p>
          <p className={styles.notice}>{event.eventTime ? formatDateTime(event.eventTime) : t('summarySource.noTime')}</p>
          <EvidenceBlock sourceCount={event.evidenceRefs.length} version={event.version} />
          <p className={styles.reference}>{t('summaryReview.sourceRefs', { refs: event.eventId })}</p>
        </>}
    </div>}
  </div>;
}
