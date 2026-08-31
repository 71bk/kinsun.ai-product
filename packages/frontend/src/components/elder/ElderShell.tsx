'use client';

import {
  Brain,
  ChatCircleDots,
  ShieldCheck,
  UserCircleGear,
  UsersThree,
} from '@phosphor-icons/react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { SignOutButton } from '@/components/SignOutButton';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import styles from './ElderShell.module.css';

const NAV_ITEMS = [
  { href: '/', label: '陪我聊天', icon: ChatCircleDots },
  { href: '/elder/memories', label: '我的記憶', icon: Brain },
  { href: '/elder/consent', label: '同意設定', icon: ShieldCheck },
  { href: '/elder/family-access', label: '家屬分享', icon: UsersThree },
] as const;

export function ElderShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  const navigation = NAV_ITEMS.map((item) => {
    const Icon = item.icon;
    const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);

    return (
      <Link
        aria-current={active ? 'page' : undefined}
        className={styles.navLink}
        href={item.href}
        key={item.href}
      >
        <Icon aria-hidden="true" size={30} weight={active ? 'fill' : 'regular'} />
        <span>{item.label}</span>
      </Link>
    );
  });

  return (
    <LocaleProvider initialLocale="zh-Hant">
      <div className={styles.shell} data-surface="voice" lang="zh-Hant-TW">
        <a className={styles.skipLink} href="#elder-main-content">
          跳到主要內容
        </a>
        <header className={styles.mobileHeader}>
          <div>
            <strong className={styles.brand}>小暖 Kinsun</strong>
            <span className={styles.brandHint}>陪伴、同意與記憶都由您決定</span>
          </div>
        </header>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarBrand}>
            <strong className={styles.brand}>小暖 Kinsun</strong>
            <span className={styles.brandHint}>陪伴、同意與記憶都由您決定</span>
          </div>
          <nav aria-label="長者功能" className={styles.desktopNav}>
            {navigation}
          </nav>
          <div className={styles.accountActions}>
            <Link className={styles.accountLink} href="/account/sign-in-methods">
              <UserCircleGear aria-hidden="true" size={28} />
              <span>登入方式</span>
            </Link>
            <SignOutButton label="登出" />
          </div>
        </aside>
        <div className={styles.mainColumn}>
          <nav aria-label="長者功能" className={styles.mobileNav}>
            {navigation}
          </nav>
          <div className={styles.content} id="elder-main-content" tabIndex={-1}>
            {children}
          </div>
          <footer className={styles.mobileAccountActions}>
            <Link className={styles.accountLink} href="/account/sign-in-methods">
              <UserCircleGear aria-hidden="true" size={28} />
              <span>登入方式</span>
            </Link>
            <SignOutButton label="登出" />
          </footer>
        </div>
      </div>
    </LocaleProvider>
  );
}
