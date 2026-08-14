'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { FamilySummaryCard } from '@/components/family/FamilySummaryCard';
import { ReportCard } from '@/components/family/ReportCard';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { StateCard } from '@/components/StateCard';
import { ErrorState } from '@/components/ui/ErrorState';
import { ApiRequestError } from '@/lib/api/client';
import { listFamilyReports, type FamilyReportView } from '@/lib/api/family-reports';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './FamilyHomePage.module.css';

const DAY_MS = 24 * 60 * 60 * 1000;

function daysAgoIso(days: number): string {
  return new Date(Date.now() - days * DAY_MS).toISOString().slice(0, 10);
}

export default function FamilyHomePage() {
  const { t, formatDateTime } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const elderId = config?.elderId ?? '';
  const [reports, setReports] = useState<FamilyReportView[] | null>(null);
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
    setErrorKey(null);
    // §10.2: never leave the previous result on screen during a refetch.
    setReports(null);
    listFamilyReports(apiConfig, elderId)
      .then(setReports)
      .catch((caught) => {
        setErrorKey(
          caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)
            ? 'error.noFamilyReportAccess'
            : 'error.loadRecentFailed',
        );
      });
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (config?.credentialStatus === 'present' && elderId) load();
  }, [config?.credentialStatus, elderId, load]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason={t('auth.credentialUnavailable')} linkLabel={t('common.signIn')} />;
  }
  if (config.credentialStatus !== 'present' || !elderId) {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }

  if (errorKey) {
    return (
      <main className={styles.page}>
        <ErrorState
          action={
            <button className={styles.retryButton} onClick={load} type="button">
              {t('common.retry')}
            </button>
          }
          description={t(errorKey)}
        />
      </main>
    );
  }

  if (!reports) {
    return (
      <main className={styles.page}>
        <Skeleton rows={5} />
      </main>
    );
  }

  const published = reports.filter((report) => report.status === 'PUBLISHED');
  const weekStart = daysAgoIso(7);
  const weeklyReports = published.filter((report) => report.periodEnd >= weekStart);
  const today = new Date().toISOString().slice(0, 10);
  const todayReport =
    published.find(
      (report) =>
        report.reportType === 'DAILY' && report.periodStart <= today && report.periodEnd >= today,
    ) ?? null;
  const lastUpdated = published.reduce<string | null>(
    (latest, report) => (!latest || report.updatedAt > latest ? report.updatedAt : latest),
    null,
  );
  const mealCount = weeklyReports.reduce(
    (count, report) =>
      count + report.items.filter((item) => item.category.toUpperCase() === 'MEAL').length,
    0,
  );
  const activityCount = weeklyReports.reduce(
    (count, report) =>
      count + report.items.filter((item) => item.category.toUpperCase() === 'ACTIVITY').length,
    0,
  );
  const importantItems = weeklyReports
    .flatMap((report) =>
      report.items
        .filter((item) => item.category.toUpperCase() === 'IMPORTANT_EVENT')
        .map((item) => ({ date: report.periodEnd, text: item.text })),
    )
    .sort((left, right) => right.date.localeCompare(left.date))
    .slice(0, 5);

  return (
    <main className={styles.page}>
      <PageHeader
        meta={t('family.meta', {
          elderId,
          updated: lastUpdated ? formatDateTime(lastUpdated) : t('family.noData'),
        })}
        title={t('family.homeTitle')}
      />

      <FamilySummaryCard title={t('family.todayTitle')}>
        {todayReport ? (
          <ReportCard report={todayReport} />
        ) : (
          <StateCard state="dataInsufficient">{t('family.todayNone')}</StateCard>
        )}
      </FamilySummaryCard>

      <FamilySummaryCard title={t('family.weekTitle')}>
        {weeklyReports.length === 0 ? (
          <p className={styles.muted}>{t('family.weekNone')}</p>
        ) : (
          <p>
            {t('family.weekSummary', {
              reports: weeklyReports.length,
              meals: mealCount,
              activities: activityCount,
            })}
          </p>
        )}
        <Link className={styles.viewAll} href="/family/reports">
          {t('family.viewAll')}
        </Link>
      </FamilySummaryCard>

      <FamilySummaryCard title={t('family.importantTitle')}>
        {importantItems.length === 0 ? (
          <p className={styles.muted}>{t('family.importantNone')}</p>
        ) : (
          <ul className={styles.importantList}>
            {importantItems.map((item, index) => (
              <li key={`${item.date}-${index}`}>
                {item.date}：{item.text}
              </li>
            ))}
          </ul>
        )}
      </FamilySummaryCard>
    </main>
  );
}
