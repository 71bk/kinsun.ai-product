'use client';

import Link from 'next/link';
import { use, useEffect, useMemo, useState } from 'react';
import { ReportCard } from '@/components/family/ReportCard';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { ApiRequestError } from '@/lib/api/client';
import { getFamilyReport, type FamilyReportView } from '@/lib/api/family-reports';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './ReportDetailPage.module.css';

export default function FamilyReportDetailPage({
  params,
}: {
  params: Promise<{ reportId: string }>;
}) {
  const { reportId } = use(params);
  const { t } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const [report, setReport] = useState<FamilyReportView | null>(null);
  const [errorKey, setErrorKey] = useState<MessageKey | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((nextConfig) => {
      if (!cancelled) setConfig(nextConfig);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (config?.credentialStatus !== 'present') return;
    let cancelled = false;
    setErrorKey(null);
    setLoading(true);
    getFamilyReport(apiConfig, reportId)
      .then((view) => {
        if (!cancelled) setReport(view);
      })
      .catch((caught) => {
        if (cancelled) return;
        // §5: unauthorized and nonexistent must read the same, so a withheld
        // (Draft/Needs-Review) report and a genuinely missing id share one message.
        setErrorKey(
          caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)
            ? 'reportDetail.notFound'
            : 'error.loadReportsFailed',
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiConfig, config?.credentialStatus, reportId]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason={t('auth.credentialUnavailable')} linkLabel={t('common.signIn')} />;
  }
  if (config.credentialStatus !== 'present') {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }

  return (
    <main className={styles.page}>
      <Link className={styles.back} href="/family/reports">
        {t('reportDetail.back')}
      </Link>
      {errorKey && <ErrorState description={t(errorKey)} />}
      {loading && !errorKey && <Skeleton rows={4} />}
      {report && !loading && !errorKey && (
        <>
          <PageHeader title={t('reportDetail.title')} />
          <ReportCard linkToDetail={false} report={report} />
        </>
      )}
    </main>
  );
}
