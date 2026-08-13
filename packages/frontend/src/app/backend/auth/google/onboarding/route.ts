import { NextRequest, NextResponse } from 'next/server';
import {
  appSessionCookieName,
  appSessionCookieOptions,
  appSessionMaxAge,
} from '@/lib/server/app-session-cookie';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { completeGoogleOnboardingWithCore } from '@/lib/server/google-oidc-core-onboarding';
import {
  googlePendingOnboardingCookieName,
  googlePendingOnboardingCookieOptions,
  parseGooglePendingOnboarding,
} from '@/lib/server/google-pending-onboarding';
import { googleDirectOidcEnabled } from '@/lib/server/google-oidc';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

export async function POST(request: NextRequest): Promise<Response> {
  if (!googleDirectOidcEnabled()) {
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
  const pending = parseGooglePendingOnboarding(
    request.cookies.get(googlePendingOnboardingCookieName())?.value,
  );
  if (!pending || (pending.intent === 'FAMILY' && !pending.invitationCode)) {
    return bffError(
      401,
      'authentication_required',
      'Google onboarding has expired',
      'GOOGLE_ONBOARDING_EXPIRED',
    );
  }
  const form = await request.formData().catch(() => null);
  const rawDisplayName = form?.get('displayName');
  const displayName = typeof rawDisplayName === 'string' ? rawDisplayName.trim() : '';
  if (pending.intent === 'ELDER' && (!displayName || displayName.length > 120)) {
    return bffError(422, 'validation_error', 'A display name is required', 'DISPLAY_NAME_REQUIRED');
  }

  try {
    const completed = await completeGoogleOnboardingWithCore(
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
    response.cookies.set(googlePendingOnboardingCookieName(), '', {
      ...googlePendingOnboardingCookieOptions(),
      expires: new Date(0),
      maxAge: 0,
    });
    return response;
  } catch {
    return noStore(
      new NextResponse(null, {
        status: 303,
        headers: { Location: '/auth/google/complete?error=onboarding_failed' },
      }),
    );
  }
}
