'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import {
  completeAssignment,
  getAssignment,
  startAssignment,
  type AssignmentView,
} from '@/lib/api/assignments';
import { ApiRequestError } from '@/lib/api/client';
import { notifyAssignmentUpdated, watchAssignmentUpdates } from '@/lib/assignment-updates';
import { useLocale } from '@/lib/i18n/locale-context';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import { AssignmentCard } from './AssignmentCard';
import styles from './AssignmentWorkbench.module.css';

export function AssignmentWorkbench({ assignmentId }: { assignmentId: string }) {
  const { t } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const api = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const [assignment, setAssignment] = useState<AssignmentView | null>(null);
  const [error, setError] = useState<'access' | 'load' | 'conflict' | null>(null);
  const [completed, setCompleted] = useState(false);
  const sequence = useRef(0);
  const ownUpdate = useRef(false);
  useEffect(() => {
    let active = true;
    void getRuntimeConfig().then((value) => {
      if (active) setConfig(value);
    });
    return () => {
      active = false;
    };
  }, []);
  const deny = useCallback(() => {
    ++sequence.current;
    setAssignment(null);
    setError('access');
  }, []);
  const load = useCallback(() => {
    const request = ++sequence.current;
    setAssignment(null);
    setError(null);
    void getAssignment(api, assignmentId)
      .then((value) => {
        if (request !== sequence.current || document.hidden) return;
        if (value.assignmentId !== assignmentId) {
          deny();
          return;
        }
        setAssignment(value);
      })
      .catch((caught) => {
        if (request !== sequence.current) return;
        setError(
          caught instanceof ApiRequestError && [401, 403, 404].includes(caught.status)
            ? 'access'
            : 'load',
        );
      });
  }, [api, assignmentId, deny]);
  useEffect(() => {
    if (config?.credentialStatus !== 'present' || completed) return;
    load();
    const refresh = () => {
      if (!document.hidden && !ownUpdate.current) load();
    };
    const clear = () => {
      ++sequence.current;
      setAssignment(null);
    };
    const visibility = () => {
      clear();
      refresh();
    };
    const unwatch = watchAssignmentUpdates(refresh);
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('focus', refresh);
    window.addEventListener('pagehide', clear);
    return () => {
      ++sequence.current;
      unwatch();
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('pagehide', clear);
    };
  }, [completed, config?.credentialStatus, load]);
  useEffect(() => {
    if (!assignment) return;
    const remaining =
      Math.min(Date.parse(assignment.scheduledEnd), Date.parse(assignment.expiresAt)) - Date.now();
    const timer = window.setTimeout(deny, Math.max(0, Math.min(remaining, 2_147_483_647)));
    return () => window.clearTimeout(timer);
  }, [assignment, deny]);
  const publish = () => {
    ownUpdate.current = true;
    notifyAssignmentUpdated();
    ownUpdate.current = false;
  };
  const finish = () => {
    ++sequence.current;
    setAssignment(null);
    setError(null);
    setCompleted(true);
    publish();
  };
  async function command(value: AssignmentView, action: 'start' | 'complete') {
    const request = sequence.current;
    try {
      const updated = await (action === 'start'
        ? startAssignment(api, value)
        : completeAssignment(api, value));
      if (request !== sequence.current || document.hidden) {
        publish();
        return;
      }
      if (action === 'complete') finish();
      else {
        setAssignment(updated);
        publish();
      }
    } catch (caught) {
      if (request === sequence.current) {
        if (caught instanceof ApiRequestError && [401, 403, 404].includes(caught.status)) deny();
        else
          setError(
            caught instanceof ApiRequestError && caught.status === 409 ? 'conflict' : 'load',
          );
      }
      throw caught;
    }
  }
  if (!config) return null;
  if (config.credentialStatus !== 'present')
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  const renderSequence = sequence.current;
  return (
    <main className={styles.page}>
      <Link className={styles.link} href="/staff" prefetch={false}>
        {t('workbench.back')}
      </Link>
      <PageHeader title={t('workbench.title')} description={t('workbench.description')} />
      {completed ? (
        <p role="status">{t('workbench.completed')}</p>
      ) : (
        <>
          {error && (
            <ErrorState
              description={t(
                error === 'access'
                  ? 'workbench.unavailable'
                  : error === 'conflict'
                    ? 'error.versionConflict'
                    : 'error.loadAssignmentsFailed',
              )}
              action={
                <button type="button" className={styles.link} onClick={load}>
                  {t('common.retry')}
                </button>
              }
            />
          )}
          {!assignment && !error && <Skeleton rows={5} />}
          {assignment && (
            <AssignmentCard
              assignment={assignment}
              key={`${assignment.assignmentId}:${assignment.version}`}
              config={api}
              onCommand={command}
              onAccessCheck={deny}
              onRecordCompleted={() => {
                if (renderSequence === sequence.current && !document.hidden) finish();
                else publish();
              }}
            />
          )}
        </>
      )}
    </main>
  );
}
