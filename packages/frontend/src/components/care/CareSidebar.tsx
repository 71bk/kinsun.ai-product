'use client';

import { CalendarCheck, UsersThree } from '@phosphor-icons/react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './CareSidebar.module.css';

const NAV_ITEMS = [
  { href: '/staff', key: 'careNav.elders', icon: UsersThree },
  { href: '/staff/assignments', key: 'careNav.assignments', icon: CalendarCheck },
] as const;

export function CareSidebar({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t } = useLocale();

  const navigation = NAV_ITEMS.map((item) => {
    const Icon = item.icon;
    /* "Elders" stays current on a specific elder's page. That used to need a
       regex excluding /dashboard/assignments, because the elder id sat directly
       under the section root; /staff/elders/<id> makes the containment explicit
       and the exclusion unnecessary (MASTER.md §13 / skill §9 nav-state-active). */
    const active =
      item.href === '/staff'
        ? pathname === '/staff' || pathname.startsWith('/staff/elders')
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
