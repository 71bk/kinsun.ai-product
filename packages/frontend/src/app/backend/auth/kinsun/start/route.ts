import { NextRequest, NextResponse } from 'next/server';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import {
  kinsunAuthCookieOptions,
  kinsunChallengeCookieName,
  kinsunInvitationCookieName,
  kinsunReturnToCookieName,
} from '@/lib/server/kinsun-auth-cookie';
import {
  kinsunNativeAuthEnabled,
  normalizeKinsunEmail,
  startKinsunEmailAuth,
} from '@/lib/server/kinsun-auth-core';
import {
  normalizeInvitationCode,
  onboardingIntent,
  strictRelativeReturnTo,
} from '@/lib/server/oauth-transaction';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function redirect(location: string): NextResponse {
  const response = new NextResponse(null, { status: 303, headers: { Location: location } });
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}
export async function POST(request: NextRequest): Promise<Response> {
  if (!kinsunNativeAuthEnabled()) return new Response(null, { status: 404 });
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  if (!request.headers.get('content-type')?.startsWith('application/x-www-form-urlencoded')) {
    return bffError(415, 'unsupported_media_type', 'Form request required', 'FORM_REQUIRED');
  }
  const form = await request.formData().catch(() => null);
  if (!form) return redirect('/sign-in?error=invalid_request');
  const intent = onboardingIntent(form.get('intent'));
  const returnTo = strictRelativeReturnTo(
    typeof form.get('returnTo') === 'string' ? String(form.get('returnTo')) : null,
  );
  const invitationCode = normalizeInvitationCode(form.get('invitationCode'));
  const email = normalizeKinsunEmail(form.get('email'));
  const displayName =
    typeof form.get('displayName') === 'string' ? String(form.get('displayName')).trim() : '';
  if (
    !intent ||
    intent === 'STAFF' ||
    !returnTo ||
    invitationCode === null ||
    !email ||
    displayName.length > 120 ||
    (intent === 'FAMILY' && !invitationCode) ||
    (intent !== 'FAMILY' && invitationCode !== undefined)
  ) {
    return redirect('/sign-in?error=invalid_request');
  }

  try {
    const started = await startKinsunEmailAuth({
      email,
      intent,
      ...(displayName ? { displayName } : {}),
    });
    const maxAge = Math.floor((Date.parse(started.expiresAt) - Date.now()) / 1000);
    if (!Number.isFinite(maxAge) || maxAge < 1 || maxAge > 900) {
      throw new Error('Kinsun challenge expiry is invalid');
    }
    const response = redirect('/auth/kinsun/verify');
    response.cookies.set(
      kinsunChallengeCookieName(),
      started.challengeToken,
      kinsunAuthCookieOptions(maxAge),
    );
    response.cookies.set(kinsunReturnToCookieName(), returnTo, kinsunAuthCookieOptions(maxAge));
    if (invitationCode) {
      response.cookies.set(
        kinsunInvitationCookieName(),
        invitationCode,
        kinsunAuthCookieOptions(maxAge),
      );
    }
    return response;
  } catch {
    return redirect('/sign-in?error=auth_unavailable');
  }
}
