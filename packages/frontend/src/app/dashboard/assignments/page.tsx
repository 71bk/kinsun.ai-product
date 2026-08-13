'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AssignmentCard } from '@/components/care/AssignmentCard';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import {
  completeAssignment,
  listAssignments,
  startAssignment,
  type AssignmentView,
} from '@/lib/api/assignments';
import { ApiRequestError } from '@/lib/api/client';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './AssignmentsPage.module.css';

function localDateValue(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function assignmentError(error: unknown): MessageKey {
  if (error instanceof ApiRequestError && (error.status === 403 || error.status === 404)) {
    return 'error.assignmentAccess';
  }
  if (error instanceof ApiRequestError && error.status === 409) return 'error.versionConflict';
  return 'error.loadAssignmentsFailed';
}

export default function AssignmentsPage() {
  const { t } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const [date, setDate] = useState(localDateValue);
  const [assignments, setAssignments] = useState<AssignmentView[] | null>(null);
  const [errorKey, setErrorKey] = useState<MessageKey | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((nextConfig) => {
      if (!cancelled) setConfig(nextConfig);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(() => {
    setAssignments(null);
    setErrorKey(null);
    listAssignments(apiConfig, date)
      .then(setAssignments)
      .catch((error) => setErrorKey(assignmentError(error)));
  }, [apiConfig, date]);

  useEffect(() => {
    if (config?.credentialStatus === 'present') load();
  }, [config?.credentialStatus, load]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason={t('auth.credentialUnavailable')} linkLabel={t('common.signIn')} />;
  }
  if (config.credentialStatus !== 'present') {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }

  async function handleCommand(assignment: AssignmentView, command: 'start' | 'complete') {
    try {
      const updated =
        command === 'start'
          ? await startAssignment(apiConfig, assignment)
          : await completeAssignment(apiConfig, assignment);
      setAssignments(
        (current) =>
          current?.map((item) => (item.assignmentId === updated.assignmentId ? updated : item)) ??
          [],
      );
    } catch (error) {
      setErrorKey(assignmentError(error));
      throw error;
    }
  }

  return (
    <main className={styles.page}>
      <PageHeader
        actions={
          <label className={styles.dateField}>
            <span>{t('assignments.date')}</span>
            <input
              onChange={(event) => setDate(event.currentTarget.value)}
              type="date"
              value={date}
            />
          </label>
        }
        description={t('assignments.description')}
        title={t('assignments.title')}
      />
      {errorKey && (
        <ErrorState
          action={
            <button className={styles.retryButton} onClick={load} type="button">
              {t('common.retry')}
            </button>
          }
          description={t(errorKey)}
        />
      )}
      {!assignments && !errorKey && <Skeleton rows={5} />}
      {assignments && assignments.length === 0 && (
        <EmptyState description={t('assignments.empty')} title={t('assignments.emptyTitle')} />
      )}
      {assignments && assignments.length > 0 && (
        <div className={styles.list}>
          {assignments.map((assignment) => (
            <AssignmentCard
              assignment={assignment}
              key={assignment.assignmentId}
              onCommand={handleCommand}
            />
          ))}
        </div>
      )}
    </main>
  );
}
