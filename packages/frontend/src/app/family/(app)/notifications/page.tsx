'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { FamilySummaryCard } from '@/components/family/FamilySummaryCard';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { ApiRequestError, createIdempotencyKey } from '@/lib/api/client';
import {
  getFamilyLinePreference,
  updateFamilyLinePreference,
  type FamilyLinePreference,
} from '@/lib/api/family-notifications';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { AUTH_STORAGE_KEYS, getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './NotificationsPage.module.css';

export default function FamilyNotificationsPage() {
  const { t } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [preference, setPreference] = useState<FamilyLinePreference | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [notice, setNotice] = useState<MessageKey | null>(null);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const saving = useRef(false);
  const saveGeneration = useRef(0);

  const load = useCallback(async (message: MessageKey | null = null) => {
    const current = ++generation.current;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setPreference(null);
    setConfig(null);
    setError(null);
    setNotice(message);
    try {
      const next = await getRuntimeConfig();
      if (current !== generation.current) return;
      setConfig(next);
      if (next.credentialStatus !== 'present' || !next.elderId) return;
      const result = await getFamilyLinePreference(next, next.elderId, request.signal);
      if (current !== generation.current) return;
      setPreference(result);
      setEnabled(result.line_enabled);
    } catch (caught) {
      if (current !== generation.current || request.signal.aborted) return;
      if (caught instanceof ApiRequestError && caught.status === 401) {
        setConfig((previous) => (previous ? { ...previous, credentialStatus: 'missing' } : null));
      } else {
        setError(
          caught instanceof ApiRequestError && [403, 404].includes(caught.status)
            ? 'notifications.accessLost'
            : 'notifications.loadFailed',
        );
      }
    }
  }, []);

  useEffect(() => {
    void load();
    const refresh = () => {
      if (!saving.current && document.visibilityState !== 'hidden') void load();
    };
    const storage = (event: StorageEvent) => {
      if (event.key === null || event.key === AUTH_STORAGE_KEYS.elderId) {
        saveGeneration.current++;
        saving.current = false;
        setBusy(false);
        void load();
      }
    };
    const interval = window.setInterval(refresh, 30_000);
    window.addEventListener('focus', refresh);
    window.addEventListener('storage', storage);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      generation.current++;
      saveGeneration.current++;
      controller.current?.abort();
      window.clearInterval(interval);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('storage', storage);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [load]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (saving.current || !config || !preference || enabled === preference.line_enabled) return;
    saving.current = true;
    const saveToken = ++saveGeneration.current;
    setBusy(true);
    setError(null);
    setNotice(null);
    const current = generation.current;
    try {
      await updateFamilyLinePreference(
        config,
        config.elderId,
        enabled,
        preference.version,
        createIdempotencyKey('family-line'),
        controller.current?.signal,
      );
      if (current === generation.current) await load('notifications.saved');
    } catch (caught) {
      if (current !== generation.current) return;
      if (caught instanceof ApiRequestError && caught.status === 401) {
        setPreference(null);
        setConfig({ ...config, credentialStatus: 'missing' });
      } else if (caught instanceof ApiRequestError && [403, 404].includes(caught.status)) {
        setPreference(null);
        setError('notifications.accessLost');
      } else {
        await load(
          caught instanceof ApiRequestError && caught.status === 409
            ? 'notifications.conflict'
            : 'notifications.saveFailed',
        );
      }
    } finally {
      if (saveToken === saveGeneration.current) {
        saving.current = false;
        setBusy(false);
      }
    }
  }

  if (config && (config.credentialStatus !== 'present' || !config.elderId)) {
    return (
      <NotLoggedIn
        reason={t(
          config.credentialStatus === 'unavailable'
            ? 'auth.credentialUnavailable'
            : 'auth.credentialMissing',
        )}
        linkLabel={t('common.signIn')}
      />
    );
  }
  return (
    <main className={styles.page}>
      <PageHeader title={t('notifications.title')} description={t('notifications.description')} />
      {notice && (
        <p className={styles.notice} role="status">
          {t(notice)}
        </p>
      )}
      {error && (
        <ErrorState
          description={t(error)}
          action={
            <button
              className={styles.button}
              type="button"
              onClick={() => void load()}
              disabled={busy}
            >
              {t('common.retry')}
            </button>
          }
        />
      )}
      {!preference && !error && <Skeleton rows={3} />}
      {preference && (
        <>
          <FamilySummaryCard title={t('notifications.lineTitle')}>
            <p className={styles.status}>
              {t(`notifications.line.${preference.line_status}` as MessageKey)}
            </p>
            {preference.line_status !== 'LINKED' && (
              <p>
                {t(
                  preference.line_link_available
                    ? 'notifications.linkInstructions'
                    : 'notifications.linkUnavailable',
                )}
              </p>
            )}
            <button
              className={styles.button}
              type="button"
              disabled={busy}
              onClick={() => void load()}
            >
              {t('notifications.refresh')}
            </button>
          </FamilySummaryCard>
          <FamilySummaryCard title={t('notifications.dailyTitle')}>
            <p>{t('notifications.schedule')}</p>
            <p>{t('notifications.privacy')}</p>
            {preference.availability !== 'READY' && (
              <p className={styles.notice}>
                {t(`notifications.availability.${preference.availability}` as MessageKey)}
              </p>
            )}
            <form onSubmit={save} className={styles.form} aria-busy={busy}>
              <label className={styles.toggle}>
                <input
                  type="checkbox"
                  checked={enabled}
                  disabled={busy || (!preference.can_enable && !preference.line_enabled)}
                  onChange={(event) => setEnabled(event.target.checked)}
                  aria-describedby="notification-help"
                />
                <span>{t('notifications.optIn')}</span>
              </label>
              <p id="notification-help" className={styles.muted}>
                {t('notifications.ownSetting')}
              </p>
              <button
                className={`${styles.button} ${styles.primary}`}
                type="submit"
                disabled={
                  busy || enabled === preference.line_enabled || (enabled && !preference.can_enable)
                }
              >
                {t(busy ? 'notifications.saving' : 'notifications.save')}
              </button>
            </form>
          </FamilySummaryCard>
        </>
      )}
    </main>
  );
}
