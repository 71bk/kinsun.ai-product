'use client';

import { ArrowRight, ClipboardText, ListChecks, UserCircle } from '@phosphor-icons/react';
import Link from 'next/link';
import { StateCard, summaryState } from '@/components/StateCard';
import type { MessageKey } from '@/lib/i18n/messages';
import type { DashboardElder } from '@/lib/api/dashboard';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './ElderCard.module.css';

export function ElderCard({ elder }: { elder: DashboardElder }) {
  const { t, locale } = useLocale();
  const metrics = elder.interactionMetrics;
  const daily = elder.dailySummary;
  const formatInteractionTime = (value: string) => new Intl.DateTimeFormat(locale, {
    timeZone: metrics?.timezone, dateStyle: 'short', timeStyle: 'short',
  }).format(new Date(value));

  return (
    <article className={styles.card}>
      <div className={styles.identity}>
        <UserCircle className={styles.avatar} size={44} weight="duotone" aria-hidden="true" />
        <div className={styles.copy}>
          <h3 className={styles.name}>{elder.elderName}</h3>
          <p className={styles.careUnit}>
            {elder.careUnitName ?? t('dashboard.careUnitUnavailable')}
          </p>
        </div>
      </div>
      <div className={styles.authorization}>
        <span className={styles.authorizationLabel}>{t('dashboard.authorizationLabel')}</span>
        <span>{elder.authorizationSummary ?? t('dashboard.authorized')}</span>
      </div>
      {metrics ? (
        <div className={styles.interactions}>
          <dl>
            <div><dt>{t('dashboard.todayInteractions')}</dt><dd>{metrics.todayCount}</dd></div>
            <div>
              <dt>{t('dashboard.lastInteraction')}</dt>
              <dd>{metrics.lastInteractionAt ? (
                <time dateTime={metrics.lastInteractionAt}>{formatInteractionTime(metrics.lastInteractionAt)}</time>
              ) : t('dashboard.noCompletedInteraction')}</dd>
            </div>
          </dl>
          <p>{t('dashboard.interactionDay', { date: metrics.localDate, timezone: metrics.timezone })}</p>
          <p>{t('dashboard.interactionAsOf', { at: formatInteractionTime(metrics.asOf) })}</p>
        </div>
      ) : <p className={styles.metricsUnavailable}>{t('dashboard.interactionsUnavailable')}</p>}
      {daily ? (
        <StateCard
          title={t('dashboard.dailySummary')}
          state={daily.summary ? summaryState(daily.summary.status) : 'dataInsufficient'}
          stateLabel={daily.summary ? t(`summaryStatus.${daily.summary.status}` as MessageKey) : undefined}
          meta={<>
            <p>{daily.localDate} · {daily.timezone}</p>
            <p>{t('dashboard.interactionAsOf', { at: new Intl.DateTimeFormat(locale, {
              timeZone: daily.timezone, dateStyle: 'short', timeStyle: 'short',
            }).format(new Date(daily.asOf)) })}</p>
          </>}
          actions={daily.summary ? (
            <Link className={styles.reviewLink} href={`/staff/elders/${elder.elderId}?tab=summaries&date=${daily.localDate}`}>
              <span>{t('dashboard.viewDailySummary')}</span>
              <ArrowRight aria-hidden="true" size={20} weight="bold" />
            </Link>
          ) : undefined}
        >
          {!daily.summary && <p>{t('dashboard.noVisibleSummary')}</p>}
        </StateCard>
      ) : <p className={styles.metricsUnavailable}>{t('dashboard.summaryUnavailable')}</p>}
      <Link className={styles.link} href={`/staff/elders/${elder.elderId}`}>
        <span>{t('dashboard.openElder')}</span>
        <ArrowRight size={20} weight="bold" aria-hidden="true" />
      </Link>
      {elder.openCareActionCount !== null && elder.openCareActionCount !== undefined && (
        <p className={styles.actionCount}>
          <ClipboardText aria-hidden="true" size={20} weight="bold" />
          <span>{t('dashboard.openCareActionCount', { count: elder.openCareActionCount })}</span>
        </p>
      )}
      {elder.pendingEventReviewCount !== null && elder.pendingEventReviewCount !== undefined && (
        <Link className={styles.reviewLink} href={`/staff/elders/${elder.elderId}?review=pending`}>
          <ListChecks aria-hidden="true" size={20} weight="bold" />
          <span>{t('dashboard.pendingEventReviewCount', { count: elder.pendingEventReviewCount })}</span>
          <ArrowRight aria-hidden="true" size={20} weight="bold" />
        </Link>
      )}
    </article>
  );
}
