'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ReportCard } from '@/components/family/ReportCard';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { FilterChip } from '@/components/ui/FilterChip';
import { ApiRequestError } from '@/lib/api/client';
import {
  listFamilyReports,
  type FamilyReportType,
  type FamilyReportView,
} from '@/lib/api/family-reports';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './FamilyReportsPage.module.css';

const REPORT_TYPES: FamilyReportType[] = ['DAILY', 'WEEKLY', 'MONTHLY', 'IMPORTANT_EVENT'];

export default function FamilyReportCenterPage() {
  const { t } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const elderId = config?.elderId ?? '';
  const [reportType, setReportType] = useState<FamilyReportType | undefined>(undefined);
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
    listFamilyReports(apiConfig, elderId, reportType)
      .then(setReports)
      .catch((caught) => {
        setErrorKey(
          caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)
            ? 'error.noFamilyReportAccess'
            : 'error.loadReportsFailed',
        );
      });
  }, [apiConfig, elderId, reportType]);

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

  return (
    <main className={styles.page}>
      <PageHeader description={t('reports.subtitle')} title={t('reports.title')} />

      <div aria-label={t('reports.filterLabel')} className={styles.filters} role="group">
        <FilterChip onClick={() => setReportType(undefined)} selected={reportType === undefined}>
          {t('reports.allTypes')}
        </FilterChip>
        {REPORT_TYPES.map((type) => (
          <FilterChip
            key={type}
            onClick={() => setReportType(type)}
            selected={reportType === type}
          >
            {t(`reportType.${type}` as MessageKey)}
          </FilterChip>
        ))}
      </div>

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
      {!reports && !errorKey && <Skeleton rows={3} />}
      {reports && reports.length === 0 && (
        <EmptyState description={t('reports.empty')} title={t('reports.emptyTitle')} />
      )}

      {reports && reports.length > 0 && (
        <div className={styles.list}>
          {reports.map((report) => (
            <ReportCard key={report.reportId} report={report} />
          ))}
        </div>
      )}
    </main>
  );
}
