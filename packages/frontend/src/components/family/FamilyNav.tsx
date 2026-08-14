'use client';

import { House, NewspaperClipping } from '@phosphor-icons/react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './FamilyNav.module.css';

const NAV_ITEMS = [
  { href: '/family', key: 'familyNav.home', icon: House },
  { href: '/family/reports', key: 'familyNav.reports', icon: NewspaperClipping },
] as const;

/** Persistent nav for the two authenticated family destinations. Scoped to the
 *  `(app)` route group so `/family/join` and `/family/sign-in` — reached before
 *  the elder relationship is established — stay exactly as they were. */
export function FamilyNav({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t } = useLocale();

  const navigation = NAV_ITEMS.map((item) => {
    const Icon = item.icon;
    const active = item.href === '/family' ? pathname === '/family' : pathname.startsWith(item.href);

    return (
      <Link
        aria-current={active ? 'page' : undefined}
        className={styles.link}
        href={item.href}
        key={item.href}
      >
        <Icon size={22} weight="bold" aria-hidden="true" />
        <span>{t(item.key)}</span>
      </Link>
    );
  });

  return (
    <div className={styles.workspace}>
      <nav aria-label={t('familyNav.label')} className={styles.nav}>
        {navigation}
      </nav>
      <div className={styles.page}>{children}</div>
    </div>
  );
}
