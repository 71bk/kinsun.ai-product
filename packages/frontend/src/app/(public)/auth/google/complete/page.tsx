import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import {
  googlePendingOnboardingCookieName,
  parseGooglePendingOnboarding,
} from '@/lib/server/google-pending-onboarding';
import { GoogleCompleteView } from './GoogleCompleteView';

export const dynamic = 'force-dynamic';

export default async function GoogleCompletePage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const [cookieStore, query] = await Promise.all([cookies(), searchParams]);
  const pending = parseGooglePendingOnboarding(
    cookieStore.get(googlePendingOnboardingCookieName())?.value,
  );
  if (!pending) redirect('/sign-in?error=google_onboarding_expired');
  return (
    <GoogleCompleteView
      error={Boolean(query.error)}
      hasInvitation={Boolean(pending.invitationCode)}
      intent={pending.intent}
    />
  );
}
