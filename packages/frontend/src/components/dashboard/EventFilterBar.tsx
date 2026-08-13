'use client';

import type { CoreCareEventStatus, CoreCareEventType, ListEventsFilters } from '@/lib/api/events';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './EventFilterBar.module.css';

export interface EventFilterBarProps {
  filters: ListEventsFilters;
  onChange: (filters: ListEventsFilters) => void;
}

const EVENT_TYPES: CoreCareEventType[] = [
  'MEAL',
  'ACTIVITY',
  'SLEEP',
  'MEDICATION_STATEMENT',
  'EMOTION_EXPRESSION',
  'SOCIAL_CONTACT',
  'EXPECTED_CONTACT_MISSED',
  'ACTIVITY_PARTICIPATION',
  'ACTIVITY_CANCELLED',
  'COMPANIONSHIP_NEED',
];
const EVENT_STATUSES: CoreCareEventStatus[] = [
  'CANDIDATE',
  'NEEDS_REVIEW',
  'VERIFIED',
  'CORRECTED',
  'REJECTED',
  'EXCLUDED',
];

export function EventFilterBar({ filters, onChange }: EventFilterBarProps) {
  const { t } = useLocale();

  return (
    <fieldset className={styles.filters}>
      <legend className={styles.legend}>{t('eventFilter.legend')}</legend>
      <label className={styles.field}>
        <span>{t('eventFilter.dateFrom')}</span>
        <input
          type="date"
          value={filters.dateFrom ?? ''}
          onChange={(event) => onChange({ ...filters, dateFrom: event.target.value || undefined })}
        />
      </label>
      <label className={styles.field}>
        <span>{t('eventFilter.dateTo')}</span>
        <input
          type="date"
          value={filters.dateTo ?? ''}
          onChange={(event) => onChange({ ...filters, dateTo: event.target.value || undefined })}
        />
      </label>
      <label className={styles.field}>
        <span>{t('eventFilter.type')}</span>
        <select
          value={filters.eventType ?? ''}
          onChange={(event) =>
            onChange({
              ...filters,
              eventType: (event.target.value || undefined) as CoreCareEventType | undefined,
            })
          }
        >
          <option value="">{t('eventFilter.allTypes')}</option>
          {/* The submitted value stays the Core enum; only the label is translated. */}
          {EVENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`eventType.${type}` as MessageKey)}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span>{t('eventFilter.status')}</span>
        <select
          value={filters.status ?? ''}
          onChange={(event) =>
            onChange({
              ...filters,
              status: (event.target.value || undefined) as CoreCareEventStatus | undefined,
            })
          }
        >
          <option value="">{t('eventFilter.officialEvents')}</option>
          {EVENT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {t(`eventStatus.${status}` as MessageKey)}
            </option>
          ))}
        </select>
      </label>
      <button className={styles.reset} onClick={() => onChange({})} type="button">
        {t('eventFilter.reset')}
      </button>
    </fieldset>
  );
}
