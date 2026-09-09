'use client';

import { CheckCircle } from '@phosphor-icons/react';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Skeleton } from '@/components/Skeleton';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { ErrorState } from '@/components/ui/ErrorState';
import type { AssignmentView } from '@/lib/api/assignments';
import { ApiRequestError, createIdempotencyKey, type ApiConfig } from '@/lib/api/client';
import {
  getServiceRecord,
  submitServiceRecord,
  type ServiceRecordSubmission,
  type ServiceRecordView,
} from '@/lib/api/service-records';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './ServiceRecordPanel.module.css';

export function ServiceRecordPanel({
  assignment,
  config,
  onAccessCheck,
}: {
  assignment: AssignmentView;
  config: ApiConfig;
  onAccessCheck: () => void;
}) {
  const { t, formatDateTime } = useLocale();
  const [record, setRecord] = useState<ServiceRecordView | null>(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [retry, setRetry] = useState(false);
  const sequence = useRef(0);
  const submitting = useRef(false);
  const attempt = useRef<{ body: ServiceRecordSubmission; key: string } | null>(null);
  const validNow = useCallback(
    () =>
      assignment.status === 'IN_PROGRESS' &&
      Date.parse(assignment.scheduledStart) <= Date.now() &&
      Date.now() < Math.min(Date.parse(assignment.scheduledEnd), Date.parse(assignment.expiresAt)),
    [assignment],
  );

  const clear = useCallback(() => {
    ++sequence.current;
    setRecord(null);
    setContent('');
    setConfirming(false);
    setRetry(false);
    attempt.current = null;
  }, []);

  const load = useCallback(async () => {
    clear();
    const request = sequence.current;
    setError(null);
    setLoading(true);
    setUnavailable(false);
    if (!validNow()) {
      setLoading(false);
      setUnavailable(true);
      return;
    }
    if (!assignment.canReadServiceRecord) {
      setLoading(false);
      return;
    }
    try {
      const result = await getServiceRecord(config, assignment.assignmentId);
      if (request !== sequence.current || document.hidden || !validNow()) return;
      setRecord(result);
    } catch (caught) {
      if (request !== sequence.current) return;
      if (caught instanceof ApiRequestError && [401, 403].includes(caught.status)) {
        setUnavailable(true);
        onAccessCheck();
      } else if (caught instanceof ApiRequestError && caught.status === 404) {
        // The API intentionally does not distinguish absent records from denied access.
        setError('serviceRecord.noAccessible');
      } else {
        setError('serviceRecord.loadError');
        setUnavailable(true);
      }
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }, [assignment, clear, config, onAccessCheck, validNow]);

  useEffect(() => {
    void load();
    const expiresIn =
      Math.min(Date.parse(assignment.scheduledEnd), Date.parse(assignment.expiresAt)) - Date.now();
    const timer = window.setTimeout(
      () => {
        clear();
        setUnavailable(true);
        setLoading(false);
      },
      Math.max(0, Math.min(expiresIn, 2_147_483_647)),
    );
    const visibility = () => {
      if (document.hidden) {
        clear();
        setUnavailable(true);
      } else void load();
    };
    document.addEventListener('visibilitychange', visibility);
    return () => {
      ++sequence.current;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [assignment, clear, load]);

  useEffect(() => {
    if (!record) return;
    // Bound retained server content even when the browser clock is inaccurate.
    const timer = window.setTimeout(() => void load(), 30_000);
    return () => window.clearTimeout(timer);
  }, [load, record]);

  function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !content.trim() ||
      content.length > 4000 ||
      !validNow() ||
      !assignment.canWriteServiceRecord
    )
      return;
    setConfirming(true);
  }

  async function submit() {
    if (submitting.current || !validNow() || !assignment.canWriteServiceRecord) return;
    const request = sequence.current;
    attempt.current ??= {
      body: { content: content.trim(), expected_assignment_version: assignment.version },
      key: createIdempotencyKey('service-record'),
    };
    submitting.current = true;
    setBusy(true);
    setError(null);
    setConfirming(false);
    try {
      const result = await submitServiceRecord(
        config,
        assignment.assignmentId,
        attempt.current.body,
        attempt.current.key,
      );
      if (request !== sequence.current || document.hidden || !validNow()) return;
      setRecord(result);
      setContent('');
      attempt.current = null;
      setRetry(false);
    } catch (caught) {
      if (request !== sequence.current) return;
      if (caught instanceof ApiRequestError && [401, 403, 404].includes(caught.status)) {
        clear();
        setUnavailable(true);
        onAccessCheck();
      } else if (caught instanceof ApiRequestError && caught.status === 409) {
        clear();
        setError('serviceRecord.conflict');
        setUnavailable(true);
      } else if (caught instanceof ApiRequestError && caught.status === 422) {
        attempt.current = null;
        setRetry(false);
        setError('serviceRecord.validationError');
      } else {
        // Keep the exact key and payload after an uncertain result. Never issue a new command silently.
        setRetry(true);
        setError('serviceRecord.submitError');
      }
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-label={t('serviceRecord.heading')}>
      <h3>{t('serviceRecord.heading')}</h3>
      <p>{t('serviceRecord.boundary')}</p>
      {error &&
        (error === 'serviceRecord.noAccessible' ? (
          <p role="status">{t(error)}</p>
        ) : (
          <ErrorState description={t(error)} />
        ))}
      {loading ? (
        <Skeleton rows={2} />
      ) : unavailable ? (
        <>
          <p role="status">{t('serviceRecord.unavailable')}</p>
          <button className={styles.secondary} type="button" onClick={() => void load()}>
            {t('common.retry')}
          </button>
        </>
      ) : record ? (
        <>
          <p className={styles.status} role="status">
            <CheckCircle aria-hidden="true" size={20} weight="bold" />
            {t('serviceRecord.saved')}
          </p>
          <p>
            {record.service_date} · {record.service_timezone}
          </p>
          <p className={styles.content}>{record.content}</p>
          <p>{t('serviceRecord.savedAt', { at: formatDateTime(record.completed_at) })}</p>
          <button className={styles.secondary} type="button" onClick={() => void load()}>
            {t('serviceRecord.refresh')}
          </button>
        </>
      ) : assignment.canWriteServiceRecord ? (
        <form onSubmit={prepare}>
          <label className={styles.field}>
            <span>{t('serviceRecord.content')}</span>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              required
              maxLength={4000}
              rows={6}
              disabled={busy || retry}
            />
          </label>
          <p className={styles.hint}>{t('serviceRecord.localOnly')}</p>
          {retry ? (
            <button
              className={styles.primary}
              disabled={busy}
              type="button"
              onClick={() => void submit()}
            >
              {t(busy ? 'serviceRecord.submitting' : 'serviceRecord.retrySame')}
            </button>
          ) : (
            <button className={styles.primary} disabled={busy || !content.trim()} type="submit">
              {t(busy ? 'serviceRecord.submitting' : 'serviceRecord.review')}
            </button>
          )}
        </form>
      ) : (
        !error && <p>{t('serviceRecord.noAccessible')}</p>
      )}
      <ConfirmationDialog
        open={confirming}
        busy={busy}
        title={t('serviceRecord.confirmTitle')}
        description={t('serviceRecord.confirmDescription')}
        confirmLabel={t('serviceRecord.submit')}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void submit()}
      />
    </section>
  );
}
