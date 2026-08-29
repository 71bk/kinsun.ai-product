'use client';

import { ArrowRight, CheckCircle, ShieldCheck, Sparkle } from '@phosphor-icons/react';
import Link from 'next/link';
import { useLocale } from '@/lib/i18n/locale-context';
import { BoundaryList } from './BoundaryList';
import { Hero } from './Hero';
import { ModuleCards } from './ModuleCards';
import { PrivacyStrip } from './PrivacyStrip';
import { RoleCards } from './RoleCards';
import styles from './Landing.module.css';

export function Landing() {
  const { t } = useLocale();

  return (
    <div className={styles.landing}>
      <div className={styles.heroFrame}>
        <Hero />
        <div className={styles.proofStrip} aria-label={t('landing.proof.label')}>
          <span>
            <Sparkle size={24} weight="fill" aria-hidden="true" />
            {t('landing.proof.voice')}
          </span>
          <span>
            <CheckCircle size={24} weight="fill" aria-hidden="true" />
            {t('landing.proof.memory')}
          </span>
          <span>
            <ShieldCheck size={24} weight="fill" aria-hidden="true" />
            {t('landing.proof.review')}
          </span>
        </div>
      </div>

      <div className={styles.moduleBand}>
        <ModuleCards />
      </div>

      <RoleCards />

      <div className={styles.trustBand}>
        <div className={styles.trustLayout}>
          <PrivacyStrip />
          <BoundaryList />
        </div>
      </div>

      <section className={styles.closing} aria-labelledby="landing-closing-title">
        <div>
          <p className={styles.closingEyebrow}>{t('landing.proof.review')}</p>
          <h2 id="landing-closing-title">{t('landing.closing.title')}</h2>
          <p>{t('landing.closing.body')}</p>
        </div>
        <Link href="/sign-in" className={styles.closingAction}>
          {t('landing.closing.cta')}
          <ArrowRight size={22} weight="bold" aria-hidden="true" />
        </Link>
      </section>
    </div>
  );
}
