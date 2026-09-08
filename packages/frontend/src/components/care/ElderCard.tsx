'use client';

import { ArrowRight, ClipboardText, ListChecks, UserCircle } from '@phosphor-icons/react';
import Link from 'next/link';
import type { DashboardElder } from '@/lib/api/dashboard';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './ElderCard.module.css';

export function ElderCard({ elder }: { elder: DashboardElder }) {
  const { t } = useLocale();

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
