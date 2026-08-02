import { cookies } from 'next/headers';
import { LineAccountLinkClient } from '@/components/LineAccountLinkClient';
import {
  lineLinkCookieName,
  normalizeLineLinkToken,
} from '@/lib/server/line-account-link';

export const dynamic = 'force-dynamic';

const ERRORS = new Set(['invalid_link', 'link_expired', 'link_failed', 'service_unavailable']);

export default function LineAccountLinkPage({
  searchParams,
}: {
  searchParams: { error?: string; status?: string };
}) {
  const hasPendingLinkToken =
    normalizeLineLinkToken(cookies().get(lineLinkCookieName())?.value) !== null;
  const initialError = ERRORS.has(searchParams.error ?? '')
    ? (searchParams.error as 'invalid_link' | 'link_expired' | 'link_failed' | 'service_unavailable')
    : undefined;
  const initialNotice = searchParams.status === 'already_linked' ? 'already_linked' : undefined;
  return (
    <LineAccountLinkClient
      hasPendingLinkToken={hasPendingLinkToken}
      initialError={initialError}
      initialNotice={initialNotice}
    />
  );
}
