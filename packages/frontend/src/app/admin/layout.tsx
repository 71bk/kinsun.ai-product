import { cookies } from 'next/headers';
import type { ReactNode } from 'react';
import { SurfaceShell } from '@/components/SurfaceShell';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { browserAuthCookieNames } from '@/lib/server/app-session-cookie';

/**
 * The administrator console runs on its own token surface (`app/tokens.css`).
 *
 * Provisioning an account is not care work: it grants a person access rather
 * than recording something about an elder, and mistaking one console for the
 * other is the expensive mistake here. There is no `/admin/sign-in` — an
 * administrator is a Kinsun email/password actor like any other staff member
 * and signs in at `/staff/sign-in`, so this layout has no route group split.
 *
 * Nothing here is an authorization signal. Core answers every `/api/v1/admin/*`
 * request from a non-ADMIN actor, or from any actor when the feature is off,
 * with the same opaque 404.
 */
export default async function AdminLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  const signedIn = browserAuthCookieNames().some((name) => Boolean(cookieStore.get(name)?.value));
  return (
    <SurfaceShell surface="admin" initialLocale={locale} signedIn={signedIn}>
      {children}
    </SurfaceShell>
  );
}
