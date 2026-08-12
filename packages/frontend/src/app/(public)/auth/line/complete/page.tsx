import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import {
  linePendingOnboardingCookieName,
  parseLinePendingOnboarding,
} from '@/lib/server/line-pending-onboarding';
import { GoogleCompleteView } from '../../google/complete/GoogleCompleteView';

export const dynamic = 'force-dynamic';

export default async function LineCompletePage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const [cookieStore, query] = await Promise.all([cookies(), searchParams]);
  const pending = parseLinePendingOnboarding(
    cookieStore.get(linePendingOnboardingCookieName())?.value,
  );
  if (!pending) redirect('/sign-in?error=line_onboarding_expired');
  return (
    <GoogleCompleteView
      error={Boolean(query.error)}
      hasInvitation={Boolean(pending.invitationCode)}
      intent={pending.intent}
      provider="LINE"
    />
  );
}
