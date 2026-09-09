'use client';

import { CheckCircle, Play } from '@phosphor-icons/react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Skeleton } from '@/components/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import { getHomeCareSchedule, type SchedulePage } from '@/lib/api/home-care-schedule';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './HomeCareSchedule.module.css';

export function HomeCareSchedule({ config, onAccessCheck }: { config: ApiConfig; onAccessCheck: () => void }) {
  const { t, locale } = useLocale();
  const [page, setPage] = useState<SchedulePage | null>(null);
  const [error, setError] = useState(false);
  const sequence = useRef(0);
  const loadedAt = useRef(0);
  const load = useCallback((cursor?: string) => {
    const request = ++sequence.current;
    const startedAt = performance.now();
    setPage(null);
    setError(false);
    void getHomeCareSchedule(config, cursor).then((result) => {
      if (request !== sequence.current || document.hidden) return;
      loadedAt.current = startedAt;
      const serverNow = Date.parse(result.as_of) + performance.now() - startedAt;
      setPage({ ...result, items: result.items.filter((row) => Date.parse(row.scheduled_end) > serverNow) });
    }).catch((caught) => {
      if (request !== sequence.current) return;
      setError(true);
      if (caught instanceof ApiRequestError && [401, 403, 404].includes(caught.status)) onAccessCheck();
    });
  }, [config, onAccessCheck]);

  useEffect(() => {
    load();
    const visibility = () => {
      ++sequence.current;
      setPage(null);
      if (!document.hidden) load();
    };
    const focus = () => load();
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('focus', focus);
    return () => {
      ++sequence.current;
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('focus', focus);
    };
  }, [load]);

  useEffect(() => {
    if (!page) return;
    // Use server time + elapsed browser time, not the browser's wall-clock timezone.
    const elapsed = performance.now() - loadedAt.current;
    const serverNow = Date.parse(page.as_of) + elapsed;
    const end = Math.min(...page.items.map((row) => Date.parse(row.scheduled_end)));
    const timer = window.setTimeout(() => load(), Math.max(0, Math.min(30_000 - elapsed, end - serverNow)));
    return () => window.clearTimeout(timer);
  }, [load, page]);

  return <section className={styles.section} aria-labelledby="home-schedule-heading">
    <div className={styles.header}>
      <h2 id="home-schedule-heading">{t('schedule.heading')}</h2>
      <button type="button" className={styles.button} onClick={() => load()}>{t('schedule.refresh')}</button>
    </div>
    <p>{t('schedule.boundary')}</p>
    {error ? <ErrorState description={t('error.loadAssignmentsFailed')} /> : !page ? <Skeleton rows={2} /> : <>
      <p>{t('schedule.asOf', { at: new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'medium', timeZone: 'UTC' }).format(new Date(page.as_of)) })} UTC</p>
      {page.items.length === 0 && <p>{t('schedule.empty')}</p>}
      <div className={styles.list}>{page.items.map((row) => {
        const Icon = row.status === 'CONFIRMED' ? CheckCircle : Play;
        const format = (value: string) => new Intl.DateTimeFormat(locale, { timeZone: row.timezone, dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
        return <article className={styles.card} key={row.assignment_id}>
          <h3>{row.display_name}</h3>
          <p className={styles.status}><Icon aria-hidden="true" size={20} weight="bold" />{t(row.status === 'CONFIRMED' ? 'schedule.confirmed' : 'schedule.inProgress')}</p>
          <p><time dateTime={row.scheduled_start}>{format(row.scheduled_start)}</time> – <time dateTime={row.scheduled_end}>{format(row.scheduled_end)}</time></p>
          <p>{row.local_date} · {row.timezone}</p>
        </article>;
      })}</div>
      {page.page.has_more && <button className={styles.button} type="button" onClick={() => load(page.page.next_cursor ?? undefined)}>{t('schedule.next')}</button>}
    </>}
  </section>;
}
