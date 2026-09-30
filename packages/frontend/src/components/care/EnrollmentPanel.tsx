'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Skeleton } from '@/components/Skeleton';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { ApiRequestError, createIdempotencyKey, type ApiConfig } from '@/lib/api/client';
import { changeEnrollment, getEnrollment, listEnrollmentHistory,
  type Enrollment, type EnrollmentAction, type EnrollmentChange } from '@/lib/api/elder-enrollments';
import type { ProfilePage } from '@/lib/api/elder-profiles';
import { publishEnrollmentChange, subscribeEnrollmentChange } from '@/lib/enrollment-invalidation';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './EnrollmentPanel.module.css';

type Pending = { action: EnrollmentAction; expected_version: number; reason: string; key: string };
const emptyHistory = (): ProfilePage<EnrollmentChange> => ({ items: [], has_more: false, next_cursor: null });

export function EnrollmentPanel({ config, enrollmentId, onAccessLost, onChanged }: {
  config: ApiConfig; enrollmentId: string; onAccessLost: () => void; onChanged: (value: Enrollment) => void;
}) {
  const { t, formatDateTime } = useLocale();
  const [record, setRecord] = useState<Enrollment | null>(null);
  const [history, setHistory] = useState(emptyHistory);
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [moreBusy, setMoreBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [conflict, setConflict] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [reload, setReload] = useState(false);
  const [saved, setSaved] = useState(false);
  const generation = useRef(0);
  const lock = useRef(false);
  const receipt = useRef<{ fingerprint: string; key: string } | null>(null);

  const fail = useCallback((cause: unknown) => {
    if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) {
      ++generation.current;
      setRecord(null); setHistory(emptyHistory()); setReason(''); setPending(null); setSaved(false); setLoading(false);
      setError('enrollment.denied'); onAccessLost();
    } else if (cause instanceof ApiRequestError && cause.status === 409) {
      setConflict(true); setPending(null); setError('enrollment.conflict');
    } else setError('enrollment.error');
  }, [onAccessLost]);

  const load = useCallback(async () => {
    const attempt = ++generation.current;
    setLoading(true); setMoreBusy(false); setError(null); setRecord(null); setHistory(emptyHistory());
    try {
      const [next, events] = await Promise.all([
        getEnrollment(config, enrollmentId), listEnrollmentHistory(config, enrollmentId),
      ]);
      if (attempt !== generation.current) return;
      setRecord(next); setHistory(events); setReason(''); setConflict(false); setPending(null);
      receipt.current = null;
    } catch (cause) { if (attempt === generation.current) fail(cause); }
    finally { if (attempt === generation.current) setLoading(false); }
  }, [config, enrollmentId, fail]);

  useEffect(() => { void load(); return () => { ++generation.current; }; }, [load]);
  useEffect(() => {
    if (!record) return;
    const check = async () => {
      if (lock.current || document.visibilityState === 'hidden') return;
      const attempt = generation.current;
      try {
        const current = await getEnrollment(config, enrollmentId);
        if (attempt !== generation.current) return;
        if (!current.can_manage && record.can_manage) {
          setReason(''); setPending(null); receipt.current = null;
        }
        if (current.version !== record.version) {
          setConflict(true); setPending(null); setError('enrollment.conflict');
        }
        setRecord((previous) => previous ? { ...previous, can_manage: current.can_manage } : null);
      } catch (cause) { if (attempt === generation.current) fail(cause); }
    };
    const timer = window.setInterval(() => void check(), 30000);
    const onFocus = () => void check();
    const unsubscribe = subscribeEnrollmentChange((elderId) => { if (elderId === record.elder_id) void check(); });
    window.addEventListener('focus', onFocus);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', onFocus); unsubscribe(); };
  }, [record, config, enrollmentId, fail]);

  function prepare(action: EnrollmentAction) {
    if (!record?.can_manage || !reason.trim() || busy || conflict) return;
    const fingerprint = JSON.stringify([enrollmentId, action, record.version, reason.trim()]);
    if (receipt.current?.fingerprint !== fingerprint)
      receipt.current = { fingerprint, key: createIdempotencyKey('enrollment') };
    setPending({ action, reason: reason.trim(), expected_version: record.version, key: receipt.current.key });
  }
  async function submit() {
    if (!pending || lock.current || conflict) return;
    lock.current = true; setBusy(true); setError(null); setSaved(false);
    const attempt = generation.current;
    try {
      const result = await changeEnrollment(config, enrollmentId, pending.action,
        { expected_version: pending.expected_version, reason: pending.reason }, pending.key);
      if (attempt !== generation.current) return;
      publishEnrollmentChange(result.elder_id);
      // A replay receipt can describe an earlier state. Fetch the current state.
      const current = await getEnrollment(config, enrollmentId);
      if (attempt !== generation.current) return;
      onChanged(current); setSaved(true); setPending(null); await load();
    } catch (cause) { if (attempt === generation.current) { setPending(null); fail(cause); } }
    finally { lock.current = false; setBusy(false); }
  }
  async function more() {
    if (!history.next_cursor || moreBusy) return;
    const attempt = generation.current; setMoreBusy(true);
    try {
      const next = await listEnrollmentHistory(config, enrollmentId, history.next_cursor);
      if (attempt === generation.current) setHistory((old) => ({ ...next, items: [...old.items, ...next.items] }));
    } catch (cause) { if (attempt === generation.current) fail(cause); }
    finally { if (attempt === generation.current) setMoreBusy(false); }
  }

  return <div className={styles.panel}>
    {error && <div className={styles.notice} role="alert">{t(error)}{' '}
      <button className={styles.button} type="button" disabled={busy} onClick={() => reason ? setReload(true) : void load()}>{t('enrollment.reload')}</button>
    </div>}
    {saved && <p role="status">{t('enrollment.saved')}</p>}
    {loading ? <Skeleton rows={4} /> : record && <>
      <section className={styles.section} aria-label={record.display_name}>
        <div className={styles.actions}><h2>{record.display_name}</h2><strong>{t(`enrollment.${record.status}`)}</strong></div>
        <p className={styles.meta}>{t('enrollment.version', { version: record.version })} · {t('enrollment.since', { at: formatDateTime(record.valid_from) })}</p>
        {record.valid_until && <p className={styles.meta}>{t('enrollment.until', { at: formatDateTime(record.valid_until) })}</p>}
        {record.ended_at && <p className={styles.meta}>{t('enrollment.endedAt', { at: formatDateTime(record.ended_at) })}</p>}
        {record.status === 'ACTIVE' && <Link href={`/staff/elders/${encodeURIComponent(record.elder_id)}`}>{t('enrollment.care')}</Link>}
        {record.status === 'SUSPENDED' && <p className={styles.notice}>{t('enrollment.paused')}</p>}
        {record.status === 'ENDED' ? <p className={styles.notice}>{t('enrollment.ended')}</p>
          : !record.can_manage ? <p>{t('enrollment.readonly')}</p>
            : ['ACTIVE', 'SUSPENDED'].includes(record.status) && <>
              <label className={styles.field}>{t('enrollment.reason')}
                <textarea maxLength={120} value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} />
                <span className={styles.meta}>{t('enrollment.reasonHint')}</span>
              </label>
              <div className={styles.actions}>
                <button type="button" className={`${styles.button} ${styles.primary}`} disabled={busy || conflict || !reason.trim()}
                  onClick={() => prepare(record.status === 'ACTIVE' ? 'suspend' : 'resume')}>
                  {t(record.status === 'ACTIVE' ? 'enrollment.suspend' : 'enrollment.resume')}
                </button>
                <button type="button" className={styles.button} disabled={busy || conflict || !reason.trim()} onClick={() => prepare('end')}>{t('enrollment.end')}</button>
              </div>
            </>}
      </section>
      <section className={styles.section}>
        <h3>{t('enrollment.history')}</h3>
        {!history.items.length && <p className={styles.meta}>{t('enrollment.noHistory')}</p>}
        <ol className={styles.history}>{history.items.map((item) => <li key={item.enrollment_change_id}>
          <strong>{t(`enrollment.${item.from_status}`)} → {t(`enrollment.${item.to_status}`)}</strong>
          <p className={styles.reason}>{item.reason}</p>
          <span className={styles.meta}>{item.changed_by_name} · {formatDateTime(item.created_at)} · {t('enrollment.version', { version: item.version })}</span>
        </li>)}</ol>
        {history.has_more && <button type="button" className={styles.button} disabled={moreBusy || busy} onClick={() => void more()}>{t('enrollment.more')}</button>}
      </section>
    </>}
    <ConfirmationDialog open={!!pending} title={pending ? t(`enrollment.${pending.action}`) : ''}
      description={pending && <div className={styles.panel}>
        <p>{record?.display_name}</p><p>{t(pending.action === 'resume' ? 'enrollment.resumeImpact' : 'enrollment.impact')}</p>
        {pending.action === 'end' && <p>{t('enrollment.endImpact')}</p>}
        <p className={styles.reason}>{t('enrollment.reason')}：{pending.reason}</p>
      </div>} tone={pending?.action === 'end' ? 'destructive' : 'default'} busy={busy}
      onConfirm={() => void submit()} onCancel={() => setPending(null)} />
    <ConfirmationDialog open={reload} title={t('enrollment.reload')} description={t('enrollment.discard')}
      onConfirm={() => { setReload(false); void load(); }} onCancel={() => setReload(false)} />
  </div>;
}
