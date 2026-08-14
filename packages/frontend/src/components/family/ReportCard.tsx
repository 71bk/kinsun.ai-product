'use client';

import Link from 'next/link';
import { familyReportState, StateCard } from '@/components/StateCard';
import type { FamilyReportView } from '@/lib/api/family-reports';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './ReportCard.module.css';

export interface ReportCardProps {
  report: FamilyReportView;
  /** Omit on the detail route itself — a page does not need a link to its own URL. */
  linkToDetail?: boolean;
}

export function ReportCard({ report, linkToDetail = true }: ReportCardProps) {
  const { t, formatDateTime } = useLocale();

  const period = t('reports.period', { start: report.periodStart, end: report.periodEnd });
  const title = t(`reportType.${report.reportType}` as MessageKey);
  const meta = (
    <>
      {period}
      {report.status !== 'WITHDRAWN' &&
        ` ｜ ${t('reports.publishedAt', {
          version: report.version,
          at: formatDateTime(report.publishedAt),
        })}`}
    </>
  );
  const actions = linkToDetail ? (
    <Link className={styles.detailLink} href={`/family/reports/${report.reportId}`}>
      {t('reports.viewDetail')}
    </Link>
  ) : undefined;

  if (report.status === 'WITHDRAWN') {
    // §10.3 / §4.2: struck-through title, and none of the old content — a
    // withdrawn report keeps no items, not even collapsed.
    return (
      <StateCard actions={actions} meta={meta} state="withdrawn" title={title}>
        {t('reports.withdrawn')}
      </StateCard>
    );
  }

  // "No data" is a first-class state with its own shape (§1, §4.2), not an
  // empty card. `dataGapNotice` is Core-authored prose, shown as-is when present.
  if (report.items.length === 0) {
    return (
      <StateCard actions={actions} meta={meta} state="dataInsufficient" title={title}>
        {report.dataGapNotice ?? t('reports.insufficient')}
      </StateCard>
    );
  }

  return (
    <StateCard actions={actions} meta={meta} state={familyReportState(report.status)} title={title}>
      <ul className={styles.items}>
        {report.items.map((item, index) => (
          <li key={`${item.category}-${index}`}>
            [{item.category}] {item.text}
            {t('common.sources', { count: item.sourceIds.length })}
          </li>
        ))}
      </ul>
    </StateCard>
  );
}
