import type { ReactNode } from 'react';
import { SurfaceShell } from '@/components/SurfaceShell';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { browserAuthCookieNames } from '@/lib/server/app-session-cookie';
import { cookies } from 'next/headers';

/* Staff sign-in is a care-surface entry point, so it uses the care token scale
   and offers the same language choice the dashboard does. */
export default async function StaffLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  /* Signing out is offered only when a session cookie exists, so the sign-in
     page itself does not carry a "sign out" control. */
  const signedIn = browserAuthCookieNames().some((name) => Boolean(cookieStore.get(name)?.value));
  return (
    <SurfaceShell surface="care" initialLocale={locale} signedIn={signedIn}>
      {children}
    </SurfaceShell>
  );
}
