'use client';

import Link from 'next/link';
import { familyReportState, StateCard } from '@/components/StateCard';
import type { FamilyReportView } from '@/lib/api/family-reports';
import { useLocale } from '@/lib/i18n/locale-context';
import { MESSAGES, type MessageKey } from '@/lib/i18n/messages';
import styles from './ReportCard.module.css';

export interface ReportCardProps {
  report: FamilyReportView;
  /** Omit on the detail route itself — a page does not need a link to its own URL. */
  linkToDetail?: boolean;
}

export function ReportCard({ report, linkToDetail = true }: ReportCardProps) {
  const { t, formatDateTime, locale } = useLocale();

  // `period_start` / `period_end` are calendar dates (YYYY-MM-DD) in the
  // contract. Build the Date from its parts so a negative UTC offset does not
  // roll the day back, and fall back to the raw value if it is not a date.
  const formatDay = (value: string): string => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    const date = match
      ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
      : new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(date);
  };
  // Item categories are free text in the contract. Label the known summary
  // categories in the reader's language; anything else shows as-is rather
  // than as a bracketed code.
  const categoryLabel = (category: string): string => {
    const key = `summaryCategory.${category.toUpperCase()}`;
    return key in MESSAGES[locale] ? t(key as MessageKey) : category;
  };

  const period = t('reports.period', {
    start: formatDay(report.periodStart),
    end: formatDay(report.periodEnd),
  });
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
            <strong>{categoryLabel(item.category)}</strong> {item.text}
            {t('common.sources', { count: item.sourceIds.length })}
          </li>
        ))}
      </ul>
    </StateCard>
  );
}
