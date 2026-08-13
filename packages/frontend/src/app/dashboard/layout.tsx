import type { ReactNode } from 'react';
import { CareSidebar } from '@/components/care/CareSidebar';
import { SurfaceShell } from '@/components/SurfaceShell';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { browserAuthCookieNames } from '@/lib/server/app-session-cookie';
import { cookies } from 'next/headers';

/* Reading the cookie here (server side) rather than in the client provider is
   what keeps SSR and the first client render in agreement — an `en` visitor
   would otherwise see a flash of Chinese on every navigation. It also opts these
   routes out of static rendering, which is correct: they are authenticated. */
export default async function CaregiverDashboardLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  const signedIn = browserAuthCookieNames().some((name) => Boolean(cookieStore.get(name)?.value));
  return (
    <SurfaceShell surface="care" initialLocale={locale} signedIn={signedIn}>
      <CareSidebar>{children}</CareSidebar>
    </SurfaceShell>
  );
}
