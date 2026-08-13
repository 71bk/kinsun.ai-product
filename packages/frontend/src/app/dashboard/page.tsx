'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { ElderOverviewList } from '@/components/dashboard/ElderOverviewList';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { SummaryMetricCard } from '@/components/ui/SummaryMetricCard';
import { ApiRequestError } from '@/lib/api/client';
import { getCaregiverDashboard, type CaregiverDashboard } from '@/lib/api/dashboard';
import { useLocale } from '@/lib/i18n/locale-context';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './DashboardPage.module.css';

export default function CaregiverDashboardPage() {
  const { t } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [dashboard, setDashboard] = useState<CaregiverDashboard | null>(null);
  // Stored as a key, not a rendered string: an error raised before the switch is
  // used must re-render in the new language, not stay frozen in the old one.
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
    if (!config) return;
    setErrorKey(null);
    // §10.2: drop the previous result before refetching. Leaving it on screen
    // would present a stale list as a finished load.
    setDashboard(null);
    getCaregiverDashboard(config)
      .then(setDashboard)
      .catch((caught) => {
        setErrorKey(
          caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)
            ? 'error.noElderAccess'
            : 'error.reload',
        );
      });
  }, [config]);

  useEffect(() => {
    if (config?.credentialStatus === 'present') load();
  }, [config, load]);

  if (!config) return null;
  if (config.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason={t('auth.credentialUnavailable')} linkLabel={t('common.signIn')} />;
  }
  if (config.credentialStatus !== 'present') {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }

  return (
    <main className={styles.page}>
      <PageHeader
        actions={
          dashboard?.actorRole === 'HOME_CARE_WORKER' ? (
            <Link className={styles.assignmentLink} href="/dashboard/assignments">
              {t('dashboard.viewAssignments')}
            </Link>
          ) : undefined
        }
        description={t('dashboard.subtitle')}
        meta={dashboard ? t('dashboard.actorMeta', { name: dashboard.actorName }) : undefined}
        title={t('dashboard.title')}
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
      {!dashboard && !errorKey && <Skeleton rows={5} />}
      {dashboard && (
        <>
          <div className={styles.metrics}>
            <SummaryMetricCard
              description={
                dashboard.hasMore
                  ? t('dashboard.loadedCountAtLeast')
                  : t('dashboard.loadedCountComplete')
              }
              label={t('dashboard.loadedCount')}
              value={dashboard.hasMore ? `${dashboard.elders.length}+` : dashboard.elders.length}
            />
          </div>
          <ElderOverviewList elders={dashboard.elders} />
        </>
      )}
    </main>
  );
}
