import { NextRequest, NextResponse } from 'next/server';
import {
  appSessionCookieName,
  appSessionCookieOptions,
  appSessionMaxAge,
} from '@/lib/server/app-session-cookie';
import {
  accessTokenCookieName,
  accessTokenCookieOptions,
  isTrustedRequestOrigin,
} from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { lineDirectOidcEnabled } from '@/lib/server/line-login-oauth';
import { completeLineOnboardingWithCore } from '@/lib/server/line-oidc-core-onboarding';
import {
  linePendingOnboardingCookieName,
  linePendingOnboardingCookieOptions,
  parseLinePendingOnboarding,
} from '@/lib/server/line-pending-onboarding';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

function clearCookie(
  response: NextResponse,
  name: string,
  options: ReturnType<typeof accessTokenCookieOptions>,
): void {
  response.cookies.set(name, '', { ...options, expires: new Date(0), maxAge: 0 });
}

export async function POST(request: NextRequest): Promise<Response> {
  if (!lineDirectOidcEnabled()) {
    return bffError(404, 'not_found', 'Resource not found', 'RESOURCE_NOT_FOUND');
  }
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  if (
    !request.headers
      .get('content-type')
      ?.toLowerCase()
      .startsWith('application/x-www-form-urlencoded')
  ) {
    return bffError(415, 'unsupported_media_type', 'Form request required', 'FORM_REQUIRED');
  }
  const pending = parseLinePendingOnboarding(
    request.cookies.get(linePendingOnboardingCookieName())?.value,
  );
  if (!pending || (pending.intent === 'FAMILY' && !pending.invitationCode)) {
    return bffError(
      401,
      'authentication_required',
      'LINE onboarding has expired',
      'LINE_ONBOARDING_EXPIRED',
    );
  }
  const form = await request.formData().catch(() => null);
  const rawDisplayName = form?.get('displayName');
  const displayName = typeof rawDisplayName === 'string' ? rawDisplayName.trim() : '';
  if (pending.intent === 'ELDER' && (!displayName || displayName.length > 120)) {
    return bffError(422, 'validation_error', 'A display name is required', 'DISPLAY_NAME_REQUIRED');
  }

  try {
    const completed = await completeLineOnboardingWithCore(
      pending,
      pending.intent === 'ELDER' ? displayName : undefined,
    );
    const response = noStore(
      new NextResponse(null, { status: 303, headers: { Location: pending.returnTo } }),
    );
    response.cookies.set(
      appSessionCookieName(),
      completed.sessionToken,
      appSessionCookieOptions(
        appSessionMaxAge(completed.idleExpiresAt, completed.absoluteExpiresAt),
      ),
    );
    clearCookie(response, accessTokenCookieName(), accessTokenCookieOptions());
    clearCookie(response, linePendingOnboardingCookieName(), linePendingOnboardingCookieOptions());
    return response;
  } catch {
    return noStore(
      new NextResponse(null, {
        status: 303,
        headers: { Location: '/auth/line/complete?error=onboarding_failed' },
      }),
    );
  }
}
