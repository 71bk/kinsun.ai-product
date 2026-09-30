'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { EnrollmentPanel } from '@/components/care/EnrollmentPanel';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { ApiRequestError } from '@/lib/api/client';
import { listEnrollments, type Enrollment } from '@/lib/api/elder-enrollments';
import type { ProfilePage } from '@/lib/api/elder-profiles';
import { useLocale } from '@/lib/i18n/locale-context';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from '@/components/care/EnrollmentPanel.module.css';

export default function EnrollmentsPage() {
  const { t } = useLocale();
  const [runtime, setRuntime] = useState<RuntimeConfig | null>(null);
  const config = useMemo(() => ({ apiBaseUrl: runtime?.apiBaseUrl ?? '/backend/core' }), [runtime?.apiBaseUrl]);
  const [page, setPage] = useState<ProfilePage<Enrollment> | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const requestBusy = useRef(false);
  useEffect(() => {
    let disposed = false;
    void getRuntimeConfig().then((value) => { if (!disposed) setRuntime(value); });
    return () => { disposed = true; };
  }, []);
  const lost = useCallback(() => {
    ++generation.current; setPage(null); setSelected(null); setError('enrollment.denied'); setBusy(false);
  }, []);
  const changed = useCallback((value: Enrollment) => {
    setPage((current) => current ? { ...current, items: current.items.map((item) => item.enrollment_id === value.enrollment_id ? value : item) } : null);
  }, []);
  const load = useCallback(async (cursor?: string | null) => {
    if (cursor && requestBusy.current) return;
    requestBusy.current = true;
    const attempt = ++generation.current; setBusy(true); setError(null);
    if (!cursor) { setSelected(null); setPage(null); }
    try {
      const next = await listEnrollments(config, cursor);
      if (attempt !== generation.current) return;
      setPage((old) => cursor && old ? { ...next, items: [...old.items, ...next.items] } : next);
    } catch (cause) {
      if (attempt !== generation.current) return;
      if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) lost();
      else setError('enrollment.error');
    } finally { if (attempt === generation.current) { requestBusy.current = false; setBusy(false); } }
  }, [config, lost]);
  useEffect(() => {
    if (runtime?.credentialStatus === 'present') void load();
    return () => { ++generation.current; };
  }, [runtime?.credentialStatus, load]);
  if (!runtime) return null;
  if (runtime.credentialStatus !== 'present') return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  return <main className={styles.page}>
    <PageHeader title={t('enrollment.title')} description={t('enrollment.subtitle')}
      actions={<Link href="/staff">{t('enrollment.back')}</Link>} />
    {error && <div className={styles.notice} role="alert">{t(error)}{' '}
      <button type="button" className={styles.button} disabled={busy} onClick={() => void load()}>{t('common.retry')}</button>
    </div>}
    {!page && busy && <Skeleton rows={4} />}
    {page && (!page.items.length ? <p>{t('enrollment.empty')}</p> : <div className={styles.layout}>
      <section aria-label={t('enrollment.list')} className={styles.list}>
        {page.items.map((item) => <button className={styles.item} type="button" key={item.enrollment_id}
          aria-pressed={selected === item.enrollment_id} onClick={() => setSelected(item.enrollment_id)}>
          <strong>{item.display_name}</strong><span>{t(`enrollment.${item.status}`)}</span>
        </button>)}
        {page.has_more && <button className={styles.button} type="button" disabled={busy} onClick={() => void load(page.next_cursor)}>{t('enrollment.more')}</button>}
      </section>
      {selected ? <EnrollmentPanel key={selected} enrollmentId={selected} config={config} onAccessLost={lost} onChanged={changed} />
        : <div className={styles.section}><p>{t('enrollment.select')}</p></div>}
    </div>)}
  </main>;
}
