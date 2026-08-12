import type { ReactNode } from 'react';
import { SurfaceShell } from '@/components/SurfaceShell';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { browserAuthCookieNames } from '@/lib/server/app-session-cookie';
import { cookies } from 'next/headers';

export default async function FamilyLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  const signedIn = browserAuthCookieNames().some((name) => Boolean(cookieStore.get(name)?.value));
  return (
    <SurfaceShell surface="family" initialLocale={locale} signedIn={signedIn}>
      {children}
    </SurfaceShell>
  );
}
