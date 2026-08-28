import { cookies } from 'next/headers';
import { Landing } from '@/components/landing/Landing';
import { PublicShell } from '@/components/public/PublicShell';
import { VoiceHomeClient } from '@/components/voice/VoiceHomeClient';
import { LOCALE_COOKIE, parseLocaleCookie } from '@/lib/i18n/locale-cookie';
import { browserAuthCookieNames } from '@/lib/server/app-session-cookie';

/**
 * Forks on session-cookie presence only — never an authorization signal, Core
 * re-authorizes every read regardless (AGENTS.md §5; same contract as
 * `SurfaceShell`'s `signedIn` prop). A signed-in visitor goes straight into
 * the canonical voice companion; everyone else gets the public landing page.
 */
export default async function HomePage() {
  const cookieStore = await cookies();
  const signedIn = browserAuthCookieNames().some((name) => Boolean(cookieStore.get(name)?.value));

  if (signedIn) {
    return <VoiceHomeClient />;
  }

  const locale = parseLocaleCookie(cookieStore.get(LOCALE_COOKIE)?.value);
  return (
    <PublicShell initialLocale={locale} signedIn={false}>
      <Landing />
    </PublicShell>
  );
}
