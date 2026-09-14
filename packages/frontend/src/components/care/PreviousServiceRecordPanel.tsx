'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Skeleton } from '@/components/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import type { AssignmentView } from '@/lib/api/assignments';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import { getPreviousServiceRecord, type PreviousServiceRecord } from '@/lib/api/service-records';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './ServiceRecordPanel.module.css';

export function PreviousServiceRecordPanel({
  assignment,
  config,
  onAccessCheck,
}: {
  assignment: AssignmentView;
  config: ApiConfig;
  onAccessCheck: () => void;
}) {
  const { t } = useLocale();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [record, setRecord] = useState<PreviousServiceRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const validNow = useCallback(
    () =>
      Boolean(assignment.canReadPreviousServiceRecord) &&
      assignment.status === 'IN_PROGRESS' &&
      Date.parse(assignment.scheduledStart) <= Date.now() &&
      Date.now() < Math.min(Date.parse(assignment.scheduledEnd), Date.parse(assignment.expiresAt)),
    [assignment],
  );

  const clear = useCallback(() => {
    ++sequence.current;
    controller.current?.abort();
    setRecord(null);
    setLoading(true);
    setFailed(false);
  }, []);

  const load = useCallback(async () => {
    clear();
    if (document.hidden) return;
    if (!validNow()) {
      onAccessCheck();
      return;
    }
    const request = sequence.current;
    const pending = new AbortController();
    controller.current = pending;
    try {
      const value = await getPreviousServiceRecord(config, assignment.assignmentId, pending.signal);
      if (request !== sequence.current || document.hidden || !validNow()) return;
      setRecord(value);
    } catch (error) {
      if (request !== sequence.current || pending.signal.aborted) return;
      if (error instanceof ApiRequestError && [401, 403, 404].includes(error.status)) {
        clear();
        setOpen(false);
        onAccessCheck();
      } else setFailed(true);
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }, [assignment.assignmentId, clear, config, onAccessCheck, validNow]);

  useEffect(() => {
    if (!open) return;
    void load();
    // Clear before every recheck, including network failures. No stale note stays visible.
    const refresh = window.setInterval(() => void load(), 30_000);
    const expiresIn =
      Math.min(Date.parse(assignment.scheduledEnd), Date.parse(assignment.expiresAt)) - Date.now();
    const expiry = window.setTimeout(
      () => {
        clear();
        setOpen(false);
        onAccessCheck();
      },
      Math.max(0, Math.min(expiresIn, 2_147_483_647)),
    );
    const visibility = () => {
      if (document.hidden) clear();
      else void load();
    };
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', clear);
    return () => {
      ++sequence.current;
      controller.current?.abort();
      window.clearInterval(refresh);
      window.clearTimeout(expiry);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', clear);
    };
  }, [assignment.expiresAt, assignment.scheduledEnd, clear, load, onAccessCheck, open]);

  if (!validNow()) return null;
  return (
    <div className={styles.panel}>
      <button
        type="button"
        className={styles.secondary}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => {
          clear();
          setOpen((value) => !value);
        }}
      >
        {t(open ? 'previousRecord.close' : 'previousRecord.open')}
      </button>
      {open && (
        <section id={id} className={styles.panel} aria-labelledby={`${id}-title`}>
          <h3 id={`${id}-title`}>{t('previousRecord.title')}</h3>
          {loading ? (
            <Skeleton rows={3} />
          ) : failed ? (
            <ErrorState
              description={t('previousRecord.loadError')}
              action={
                <button type="button" className={styles.secondary} onClick={() => void load()}>
                  {t('common.retry')}
                </button>
              }
            />
          ) : record ? (
            <>
              <p className={styles.hint}>
                {t('previousRecord.source', {
                  date: record.service_date,
                  timezone: record.service_timezone,
                  version: record.version,
                })}
              </p>
              <p className={styles.content}>{record.content}</p>
            </>
          ) : (
            <p role="status">{t('previousRecord.empty')}</p>
          )}
        </section>
      )}
    </div>
  );
}
