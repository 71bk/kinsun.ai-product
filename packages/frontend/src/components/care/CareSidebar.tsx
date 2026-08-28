'use client';

import { CalendarCheck, UsersThree } from '@phosphor-icons/react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './CareSidebar.module.css';

const NAV_ITEMS = [
  { href: '/dashboard', key: 'careNav.elders', icon: UsersThree },
  { href: '/dashboard/assignments', key: 'careNav.assignments', icon: CalendarCheck },
] as const;

export function CareSidebar({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t } = useLocale();

  const navigation = NAV_ITEMS.map((item) => {
    const Icon = item.icon;
    const active =
      item.href === '/dashboard'
        ? pathname === '/dashboard' ||
          (pathname !== '/dashboard/assignments' && /^\/dashboard\/[^/]+$/.test(pathname))
        : pathname.startsWith(item.href);

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
      <aside className={styles.sidebar}>
        <nav aria-label={t('careNav.label')} className={styles.desktopNav}>
          {navigation}
        </nav>
      </aside>
      <div className={styles.mainColumn}>
        <nav aria-label={t('careNav.label')} className={styles.mobileNav}>
          {navigation}
        </nav>
        <div className={styles.page}>{children}</div>
      </div>
    </div>
  );
}
