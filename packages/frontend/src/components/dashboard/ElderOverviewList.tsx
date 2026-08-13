'use client';

import { useMemo, useState } from 'react';
import { ElderCard } from '@/components/care/ElderCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { SearchField } from '@/components/ui/SearchField';
import type { DashboardElder } from '@/lib/api/dashboard';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './ElderOverviewList.module.css';

export interface ElderOverviewListProps {
  elders: DashboardElder[];
}

export function ElderOverviewList({ elders }: ElderOverviewListProps) {
  const { t } = useLocale();
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return elders;
    return elders.filter((elder) =>
      [elder.elderName, elder.careUnitName, elder.authorizationSummary]
        .filter((value): value is string => Boolean(value))
        .some((value) => value.toLocaleLowerCase().includes(normalized)),
    );
  }, [elders, query]);

  if (elders.length === 0) {
    return <EmptyState description={t('dashboard.empty')} title={t('dashboard.emptyTitle')} />;
  }

  return (
    <section aria-labelledby="elder-list-title" className={styles.section}>
      <div className={styles.toolbar}>
        <div>
          <h2 className={styles.title} id="elder-list-title">
            {t('dashboard.elderListTitle')}
          </h2>
          <p aria-live="polite" className={styles.resultCount}>
            {t('dashboard.filteredCount', { count: filtered.length })}
          </p>
        </div>
        <SearchField
          hideLabel
          label={t('dashboard.searchLabel')}
          onChange={setQuery}
          placeholder={t('dashboard.searchPlaceholder')}
          value={query}
        />
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          description={t('dashboard.noSearchResults')}
          title={t('dashboard.noSearchResultsTitle')}
        />
      ) : (
        <div className={styles.grid}>
          {filtered.map((elder) => (
            <ElderCard elder={elder} key={elder.elderId} />
          ))}
        </div>
      )}
    </section>
  );
}
