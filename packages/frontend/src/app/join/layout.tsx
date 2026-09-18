import { cookies } from 'next/headers';
import type { ReactNode } from 'react';
import { SurfaceShell } from '@/components/SurfaceShell';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';

/**
 * Invitation activation is a care-surface entry point, like `/staff/sign-in`:
 * the person completing it is about to become a care worker, and should land in
 * the token scale they will keep using rather than the administrator console
 * that issued the link.
 *
 * `signedIn` is hard-coded false. Whoever opens this link has no session yet,
 * and offering "sign out" on an activation page would be nonsense; an existing
 * App Session in the browser is irrelevant here because the credential, not the
 * cookie, is what Core authenticates.
 */
export default async function JoinLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  return (
    <SurfaceShell surface="care" initialLocale={locale} signedIn={false}>
      {children}
    </SurfaceShell>
  );
}
