'use client';

import { ClipboardText, DeviceTablet, ShieldCheck, UserPlus } from '@phosphor-icons/react';
import Link from 'next/link';
import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import {
  createAccountlessElder,
  issueAssistedSession,
  type CareProfileCategory,
} from '@/lib/api/assisted-elders';
import { getCaregiverDashboard, type CaregiverDashboard } from '@/lib/api/dashboard';
import { useLocale } from '@/lib/i18n/locale-context';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './CreateElderPage.module.css';

type ProfileText = Record<CareProfileCategory, string>;

const EMPTY_PROFILE: ProfileText = {
  HEALTH_CONDITION: '',
  MEDICATION: '',
  ALLERGY: '',
  CARE_PRECAUTION: '',
};

function profileEntries(profile: ProfileText) {
  return (Object.entries(profile) as Array<[CareProfileCategory, string]>).flatMap(
    ([category, value]) =>
      value
        .split(/\r?\n/)
        .map((content) => content.trim())
        .filter(Boolean)
        .map((content) => ({ category, content })),
  );
}

export default function CreateAccountlessElderPage() {
  const { t, formatDateTime } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [dashboard, setDashboard] = useState<CaregiverDashboard | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [preferredName, setPreferredName] = useState('');
  const [preferredLanguage, setPreferredLanguage] = useState<
    'ZH_TW' | 'NAN_TW' | 'HAK_TW' | 'EN_US' | 'MIXED'
  >('ZH_TW');
  const [primaryCareSetting, setPrimaryCareSetting] = useState<'DAYCARE' | 'COMMUNITY'>('DAYCARE');
  const [careUnitId, setCareUnitId] = useState('');
  const [profile, setProfile] = useState<ProfileText>(EMPTY_PROFILE);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [handoff, setHandoff] = useState<{
    displayName: string;
    url: string;
    expiresAt: string;
  } | null>(null);

  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((runtime) => {
      if (cancelled) return;
      setConfig(runtime);
      if (runtime.credentialStatus !== 'present') return;
      void getCaregiverDashboard(runtime).then((result) => {
        if (cancelled) return;
        setDashboard(result);
        setCareUnitId(result.careUnitIds[0] ?? '');
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!config) return <Skeleton rows={6} />;
  if (config.credentialStatus !== 'present') {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }
  if (!dashboard) return <Skeleton rows={6} />;
  if (dashboard.actorRole !== 'DAYCARE_CARE_WORKER' || dashboard.careUnitIds.length === 0) {
    return (
      <main className={styles.page}>
        <ErrorState description={t('elderCreate.noCareUnit')} />
      </main>
    );
  }
  const activeDashboard = dashboard;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(false);
    setCopied(false);
    try {
      const elder = await createAccountlessElder(apiConfig, {
        organizationId: activeDashboard.tenantId,
        careUnitId,
        displayName,
        preferredName,
        preferredLanguage,
        primaryCareSetting,
        careProfile: profileEntries(profile),
      });
      const issued = await issueAssistedSession(apiConfig, elder.elder_id);
      setHandoff({
        displayName: elder.display_name,
        url: `${window.location.origin}/elder/pair#${issued.pairing_token}`,
        expiresAt: issued.pairing_expires_at,
      });
    } catch {
      setError(true);
    } finally {
      setSubmitting(false);
    }
  }

  if (handoff) {
    return (
      <main className={styles.page}>
        <PageHeader
          description={t('elderCreate.successDescription')}
          title={t('elderCreate.successTitle')}
        />
        <section className={styles.successCard} aria-live="polite">
          <span className={styles.successIcon}>
            <DeviceTablet aria-hidden="true" size={32} weight="fill" />
          </span>
          <h2>{handoff.displayName}</h2>
          <label className={styles.label} htmlFor="tablet-handoff-link">
            {t('elderCreate.tabletLink')}
          </label>
          <div className={styles.copyRow}>
            <input id="tablet-handoff-link" readOnly value={handoff.url} />
            <button
              className={styles.secondaryButton}
              onClick={() => {
                void navigator.clipboard.writeText(handoff.url).then(() => setCopied(true));
              }}
              type="button"
            >
              <ClipboardText aria-hidden="true" size={20} />
              {t('elderCreate.copy')}
            </button>
          </div>
          {copied && <p className={styles.successText}>{t('elderCreate.copied')}</p>}
          <p className={styles.meta}>{t('elderCreate.expiry', { at: formatDateTime(handoff.expiresAt) })}</p>
          <p className={styles.securityNotice}>
            <ShieldCheck aria-hidden="true" size={22} weight="fill" />
            {t('elderCreate.securityNotice')}
          </p>
          <Link className={styles.backLink} href="/staff">
            {t('elderCreate.back')}
          </Link>
        </section>
      </main>
    );
  }

  const profileFields: Array<{
    category: CareProfileCategory;
    label: Parameters<typeof t>[0];
  }> = [
    { category: 'HEALTH_CONDITION', label: 'elderCreate.conditions' },
    { category: 'MEDICATION', label: 'elderCreate.medications' },
    { category: 'ALLERGY', label: 'elderCreate.allergies' },
    { category: 'CARE_PRECAUTION', label: 'elderCreate.precautions' },
  ];

  return (
    <main className={styles.page}>
      <PageHeader
        actions={
          <Link className={styles.backLink} href="/staff">
            {t('elderCreate.back')}
          </Link>
        }
        description={t('elderCreate.subtitle')}
        title={t('elderCreate.title')}
      />
      {error && <ErrorState description={t('elderCreate.failed')} />}
      <form className={styles.form} onSubmit={(event) => void submit(event)}>
        <section className={styles.card}>
          <div className={styles.sectionTitle}>
            <UserPlus aria-hidden="true" size={24} weight="fill" />
            <h2>{t('elderCreate.title')}</h2>
          </div>
          <div className={styles.grid}>
            <label className={styles.field}>
              <span>{t('elderCreate.displayName')}</span>
              <input
                maxLength={120}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                value={displayName}
              />
            </label>
            <label className={styles.field}>
              <span>{t('elderCreate.preferredName')}</span>
              <input
                maxLength={80}
                onChange={(event) => setPreferredName(event.target.value)}
                value={preferredName}
              />
            </label>
            <label className={styles.field}>
              <span>{t('elderCreate.language')}</span>
              <select
                onChange={(event) => setPreferredLanguage(event.target.value as typeof preferredLanguage)}
                value={preferredLanguage}
              >
                <option value="ZH_TW">中文（臺灣）</option>
                <option value="NAN_TW">臺語</option>
                <option value="HAK_TW">客語</option>
                <option value="MIXED">混合語言</option>
                <option value="EN_US">English</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>{t('elderCreate.careSetting')}</span>
              <select
                onChange={(event) => setPrimaryCareSetting(event.target.value as typeof primaryCareSetting)}
                value={primaryCareSetting}
              >
                <option value="DAYCARE">{t('careSetting.DAYCARE')}</option>
                <option value="COMMUNITY">{t('careSetting.COMMUNITY')}</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>{t('elderCreate.careUnit')}</span>
              <select onChange={(event) => setCareUnitId(event.target.value)} value={careUnitId}>
                {activeDashboard.careUnitIds.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        <section className={styles.card}>
          <div className={styles.sectionTitle}>
            <ShieldCheck aria-hidden="true" size={24} weight="fill" />
            <h2>Care Profile</h2>
          </div>
          <p className={styles.notice}>{t('elderCreate.recordedNotice')}</p>
          <div className={styles.profileGrid}>
            {profileFields.map((field) => (
              <label className={styles.field} key={field.category}>
                <span>{t(field.label)}</span>
                <textarea
                  aria-describedby={`${field.category}-hint`}
                  maxLength={4000}
                  onChange={(event) =>
                    setProfile((current) => ({ ...current, [field.category]: event.target.value }))
                  }
                  rows={4}
                  value={profile[field.category]}
                />
                <small id={`${field.category}-hint`}>{t('elderCreate.onePerLine')}</small>
              </label>
            ))}
          </div>
        </section>

        <button className={styles.primaryButton} disabled={submitting} type="submit">
          {submitting ? t('elderCreate.submitting') : t('elderCreate.submit')}
        </button>
      </form>
    </main>
  );
}
