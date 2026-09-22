'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { ApiRequestError, createIdempotencyKey, type ApiConfig } from '@/lib/api/client';
import { listSummaries, type SummaryView } from '@/lib/api/summaries';
import { commandStaffReport, createReportFromSummary, loadReportWorkspace,
  type StaffReport, type StaffReportWorkspace } from '@/lib/api/staff-reports';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './StaffReportPanel.module.css';

type Pending = { report: StaffReport; action: 'publish' | 'withdraw'; key: string };

export function StaffReportPanel({ apiConfig, elderId, canPublish, canWithdraw, onAccessCheck }: {
  apiConfig: ApiConfig; elderId: string; canPublish: boolean; canWithdraw: boolean;
  onAccessCheck: () => void;
}) {
  const { t } = useLocale();
  const [workspace, setWorkspace] = useState<StaffReportWorkspace | null>(null);
  const [summaries, setSummaries] = useState<SummaryView[]>([]);
  const [summaryId, setSummaryId] = useState('');
  const [recipients, setRecipients] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [notice, setNotice] = useState<MessageKey | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const generation = useRef(0);
  const commandBusy = useRef(false);
  const draftKey = useRef<string | null>(null);

  const handleError = useCallback((caught: unknown) => {
    if (caught instanceof ApiRequestError && [401, 403, 404].includes(caught.status)) {
      setWorkspace(null); setSummaries([]); setPending(null);
      setError('staffReport.denied'); onAccessCheck();
    } else {
      setError(caught instanceof ApiRequestError && caught.status === 409 ? 'staffReport.conflict'
        : caught instanceof ApiRequestError && caught.status === 422 ? 'staffReport.scopeChanged'
        : 'staffReport.error');
    }
  }, [onAccessCheck]);

  const load = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true); setWorkspace(null); setSummaries([]); setPending(null);
    setSummaryId(''); setRecipients([]); setError(null); draftKey.current = null;
    try {
      const [next, source] = await Promise.all([
        loadReportWorkspace(apiConfig, elderId), listSummaries(apiConfig, elderId),
      ]);
      if (current !== generation.current) return;
      setWorkspace(next);
      setSummaries(source.items.filter(item => ['READY', 'PUBLISHED'].includes(item.status)
        && item.conflictFlags.length === 0 && item.items.every(row => row.dataStatus === 'PRESENT')));
    } catch (caught) { if (current === generation.current) handleError(caught); }
    finally { if (current === generation.current) setLoading(false); }
  }, [apiConfig, elderId, handleError]);

  useEffect(() => { void load(); return () => { generation.current += 1; }; }, [load]);

  async function createDraft() {
    const source = summaries.find(item => item.summaryId === summaryId);
    if (!source || !recipients.length || commandBusy.current) return;
    commandBusy.current = true; setBusy(true); setError(null); setNotice(null);
    const current = generation.current;
    draftKey.current ??= createIdempotencyKey('staff-report-draft');
    try {
      await createReportFromSummary(apiConfig, elderId, source.summaryId, source.version,
        recipients, draftKey.current);
      if (current !== generation.current) return;
      setNotice('staffReport.created'); await load();
    } catch (caught) { if (current === generation.current) handleError(caught); }
    finally { commandBusy.current = false; setBusy(false); }
  }

  async function confirmCommand() {
    if (!pending || commandBusy.current) return;
    if (pending.action === 'publish' && !reviewed) { setError('staffReport.reviewRequired'); return; }
    commandBusy.current = true; setBusy(true); setError(null); setNotice(null);
    const current = generation.current;
    try {
      await commandStaffReport(apiConfig, elderId, pending.report, pending.action, pending.key);
      if (current !== generation.current) return;
      setNotice(pending.action === 'publish' ? 'staffReport.published' : 'staffReport.withdrawn');
      setPending(null); await load();
    } catch (caught) { if (current === generation.current) handleError(caught); }
    finally { commandBusy.current = false; setBusy(false); }
  }

  function recipientNames(report: StaffReport) {
    return report.recipient_scope_ids.map(id => workspace?.recipients.find(
      recipient => recipient.relationship_id === id)?.display_name ?? t('staffReport.recipientUnavailable'));
  }
  function reportContent(report: StaffReport) {
    return <>
      <p>{report.period_start} · {t('common.version', { version: report.version })}</p>
      <p>{t('staffReport.recipients')}: {recipientNames(report).join('、')}</p>
      {report.items.length ? <ul>{report.items.map((item, index) => <li key={index}>{item.text}</li>)}</ul>
        : <p>{t('staffReport.noData')}</p>}
      {report.data_gap_notice && <p>{report.data_gap_notice}</p>}
    </>;
  }
  const selected = summaries.find(item => item.summaryId === summaryId);

  return <div className={styles.panel}>
    <header><h2>{t('staffReport.title')}</h2><p>{t('staffReport.intro')}</p></header>
    <button className={styles.secondary} disabled={busy || loading} type="button" onClick={() => void load()}>
      {t('staffReport.refresh')}
    </button>
    {loading && <p role="status">{t('common.loading')}</p>}
    {error && <p className={styles.error} role="alert">{t(error)}</p>}
    {notice && <p role="status">{t(notice)}</p>}
    {workspace && <>
      <form className={styles.card} onSubmit={event => { event.preventDefault(); void createDraft(); }}>
        <label className={styles.field}>{t('staffReport.source')}
          <select value={summaryId} disabled={busy} onChange={event => {
            setSummaryId(event.target.value); draftKey.current = null;
          }}>
            <option value="">{t('staffReport.choose')}</option>
            {summaries.map(summary => <option key={summary.summaryId} value={summary.summaryId}>
              {t('staffReport.sourceVersion', { date: summary.date, version: summary.version })}
            </option>)}
          </select>
        </label>
        {!summaries.length && <p>{t('staffReport.noneSummaries')}</p>}
        {selected && <div className={styles.preview}>
          <ul>{selected.items.map((item, index) => <li key={index}>{item.text}</li>)}</ul>
          {selected.missingFields.length > 0 && <p>{t('staffReport.gaps')}</p>}
        </div>}
        <fieldset disabled={busy} className={styles.recipients}>
          <legend>{t('staffReport.recipients')}</legend>
          {workspace.recipients.map(recipient => <label className={styles.check} key={recipient.relationship_id}>
            <input type="checkbox" checked={recipients.includes(recipient.relationship_id)} onChange={event => {
              setRecipients(current => event.target.checked ? [...current, recipient.relationship_id]
                : current.filter(id => id !== recipient.relationship_id)); draftKey.current = null;
            }} />{recipient.display_name}
          </label>)}
          {!workspace.recipients.length && <p>{t('staffReport.noneRecipients')}</p>}
        </fieldset>
        <button className={styles.primary} disabled={busy || !selected || !recipients.length} type="submit">
          {t(busy ? 'staffReport.creating' : 'staffReport.create')}
        </button>
      </form>
      <h3>{t('staffReport.list')}</h3>
      {!workspace.reports.length && <p>{t('staffReport.empty')}</p>}
      {workspace.reports.map(report => {
        const available = report.recipient_scope_ids.length > 0 && report.recipient_scope_ids.every(id =>
          workspace.recipients.some(recipient => recipient.relationship_id === id));
        return <article className={styles.card} key={report.report_id}>
          <h3>{report.period_start} · {t(('summaryStatus.' + report.status) as MessageKey)}</h3>
          {reportContent(report)}
          {['DRAFT', 'NEEDS_REVIEW'].includes(report.status) && <>
            <p>{t('staffReport.reviewNotice')}</p>
            {!available && <p>{t('staffReport.recipientUnavailable')}</p>}
            {canPublish && report.report_type === 'DAILY' && <button className={styles.secondary}
              disabled={busy || !available} type="button" onClick={() => {
                setReviewed(false); setError(null);
                setPending({ report, action: 'publish', key: createIdempotencyKey('staff-report-publish') });
              }}>{t('staffReport.publish')}</button>}
          </>}
          {canWithdraw && report.status === 'PUBLISHED' && <button className={styles.secondary}
            disabled={busy} type="button" onClick={() => {
              setError(null); setPending({ report, action: 'withdraw', key: createIdempotencyKey('staff-report-withdraw') });
            }}>{t('staffReport.withdraw')}</button>}
        </article>;
      })}
    </>}
    <ConfirmationDialog open={pending !== null} busy={busy}
      title={t(pending?.action === 'withdraw' ? 'staffReport.withdrawTitle' : 'staffReport.publishTitle')}
      confirmLabel={t(pending?.action === 'withdraw' ? 'staffReport.withdraw' : 'staffReport.publish')}
      tone={pending?.action === 'withdraw' ? 'destructive' : 'default'}
      description={<div className={styles.confirmation}>
        <p>{t(pending?.action === 'withdraw' ? 'staffReport.withdrawDescription' : 'staffReport.publishDescription')}</p>
        {pending && reportContent(pending.report)}
        {pending?.action === 'publish' && <label className={styles.check}>
          <input type="checkbox" checked={reviewed} disabled={busy} onChange={event => setReviewed(event.target.checked)} />
          {t('staffReport.review')}
        </label>}
        {pending && error && <p role="alert">{t(error)}</p>}
      </div>}
      onCancel={() => { setPending(null); setReviewed(false); setError(null); }}
      onConfirm={() => void confirmCommand()} />
  </div>;
}
