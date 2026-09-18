'use client';

import { ArrowUpRight, Buildings } from '@phosphor-icons/react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { getActorProfile } from '@/lib/api/dashboard';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './AdminEntryLink.module.css';

/**
 * Offers the administrator console to an actor who can actually use it.
 *
 * This is presentation, not permission. Core answers every `/api/v1/admin/*`
 * request from a non-ADMIN with an opaque 404 regardless of what chrome the
 * browser drew, so a wrong answer here costs a dead link, never access. The
 * check exists so a care worker is not shown a door that 404s on them.
 *
 * Rendered only where a dual-role account is conceivable (see `SurfaceShell`).
 * The family surface never mounts it, so family pages pay nothing for a role
 * their actor cannot hold.
 */
export function AdminEntryLink() {
  const { t } = useLocale();
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getActorProfile({ apiBaseUrl: '/backend/core' })
      .then((profile) => {
        if (!cancelled) setIsAdmin(profile.role === 'ADMIN');
      })
      // A failure here means the chrome stays as it was. Surfacing a broken
      // session through a navigation link would be the wrong messenger; the
      // page's own data load reports that.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!isAdmin) return null;

  return (
    <Link className={styles.link} href="/admin">
      <Buildings aria-hidden="true" size={20} weight="fill" />
      <span>{t('surface.adminEntry')}</span>
      <ArrowUpRight aria-hidden="true" size={16} weight="bold" />
    </Link>
  );
}
