'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Skeleton } from '@/components/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import type { AssignmentView } from '@/lib/api/assignments';
import { listCareActions, type CareActionListView } from '@/lib/api/care-actions';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './ServiceRecordPanel.module.css';

export function AssignmentFollowUps({
  assignment,
  config,
  onAccessCheck,
}: {
  assignment: AssignmentView;
  config: ApiConfig;
  onAccessCheck: () => void;
}) {
  const { t, formatDateTime } = useLocale();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<CareActionListView | null>(null);
  const [failed, setFailed] = useState(false);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const validNow = useCallback(
    () =>
      Boolean(assignment.canReadCareActions) &&
      assignment.status === 'IN_PROGRESS' &&
      Date.parse(assignment.scheduledStart) <= Date.now() &&
      Date.now() < Math.min(Date.parse(assignment.scheduledEnd), Date.parse(assignment.expiresAt)),
    [assignment],
  );
  const clear = useCallback(() => {
    ++sequence.current;
    controller.current?.abort();
    setPage(null);
    setFailed(false);
  }, []);
  const load = useCallback(
    async (cursor?: string) => {
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
        const result = await listCareActions(config, assignment.elderId, {
          assignmentId: assignment.assignmentId,
          statuses: ['OPEN', 'IN_PROGRESS', 'POSTPONED'],
          cursor,
          signal: pending.signal,
        });
        if (request === sequence.current && !document.hidden && validNow()) setPage(result);
      } catch (error) {
        if (request !== sequence.current || pending.signal.aborted) return;
        if (error instanceof ApiRequestError && [401, 403, 404].includes(error.status)) {
          clear();
          setOpen(false);
          onAccessCheck();
        } else setFailed(true);
      }
    },
    [assignment.assignmentId, assignment.elderId, clear, config, onAccessCheck, validNow],
  );
  useEffect(() => {
    if (!open) return;
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    const expiry = window.setTimeout(
      () => {
        clear();
        setOpen(false);
        onAccessCheck();
      },
      Math.max(
        0,
        Math.min(
          2_147_483_647,
          Math.min(Date.parse(assignment.scheduledEnd), Date.parse(assignment.expiresAt)) -
            Date.now(),
        ),
      ),
    );
    const visibility = () => {
      if (document.hidden) clear();
      else void load();
    };
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', clear);
    window.addEventListener('focus', visibility);
    return () => {
      ++sequence.current;
      controller.current?.abort();
      window.clearInterval(timer);
      window.clearTimeout(expiry);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', clear);
      window.removeEventListener('focus', visibility);
    };
  }, [assignment.expiresAt, assignment.scheduledEnd, clear, load, onAccessCheck, open]);
  if (!validNow()) return null;
  return (
    <div className={styles.panel}>
      <button
        className={styles.secondary}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => {
          clear();
          setOpen(!open);
        }}
      >
        {t(open ? 'workbench.closeTasks' : 'workbench.openTasks')}
      </button>
      {open && (
        <section id={id} className={styles.panel} aria-labelledby={`${id}-title`}>
          <h3 id={`${id}-title`}>{t('workbench.tasks')}</h3>
          <p className={styles.hint}>{t('workbench.tasksHint')}</p>
          {failed ? (
            <ErrorState
              description={t('workbench.tasksError')}
              action={
                <button className={styles.secondary} type="button" onClick={() => void load()}>
                  {t('common.retry')}
                </button>
              }
            />
          ) : !page ? (
            <Skeleton rows={3} />
          ) : (
            <>
              {page.items.length === 0 && <p role="status">{t('workbench.noTasks')}</p>}
              {page.items.map((action) => (
                <article key={action.careActionId} className={styles.panel}>
                  <h4>{action.title}</h4>
                  <p>{t(`careActionStatus.${action.status}`)}</p>
                  <p>
                    {t('careAction.dueAt')}: {formatDateTime(action.dueAt)}
                  </p>
                  {action.description && <p className={styles.content}>{action.description}</p>}
                </article>
              ))}
              {page.hasMore && page.nextCursor && (
                <button
                  className={styles.secondary}
                  type="button"
                  onClick={() => void load(page.nextCursor ?? undefined)}
                >
                  {t('workbench.nextTasks')}
                </button>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
