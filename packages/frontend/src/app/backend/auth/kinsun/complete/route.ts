import { NextRequest, NextResponse } from 'next/server';
import {
  appSessionCookieName,
  appSessionCookieOptions,
  appSessionMaxAge,
} from '@/lib/server/app-session-cookie';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import {
  clearKinsunAuthCookies,
  kinsunChallengeCookieName,
  kinsunInvitationCookieName,
  kinsunReturnToCookieName,
  normalizeKinsunChallenge,
} from '@/lib/server/kinsun-auth-cookie';
import {
  completeKinsunEmailAuth,
  KinsunCoreAuthError,
  kinsunNativeAuthEnabled,
} from '@/lib/server/kinsun-auth-core';
import { normalizeInvitationCode, strictRelativeReturnTo } from '@/lib/server/oauth-transaction';

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
  const form = await request.formData().catch(() => null);
  const verificationCode =
    form && typeof form.get('verificationCode') === 'string'
      ? String(form.get('verificationCode')).trim()
      : '';
  const password =
    form && typeof form.get('password') === 'string' ? String(form.get('password')) : '';
  const passwordConfirmation =
    form && typeof form.get('passwordConfirmation') === 'string'
      ? String(form.get('passwordConfirmation'))
      : '';
  const challengeToken = normalizeKinsunChallenge(
    request.cookies.get(kinsunChallengeCookieName())?.value,
  );
  const invitationCode = normalizeInvitationCode(
    request.cookies.get(kinsunInvitationCookieName())?.value,
  );
  const returnTo = strictRelativeReturnTo(
    request.cookies.get(kinsunReturnToCookieName())?.value ?? null,
  );
  if (
    !challengeToken ||
    !returnTo ||
    invitationCode === null ||
    !/^[0-9]{6}$/.test(verificationCode) ||
    password !== passwordConfirmation ||
    password.length < 12 ||
    password.length > 128 ||
    Buffer.byteLength(password, 'utf8') > 1024 ||
    password.includes('\0')
  ) {
    return redirect('/auth/kinsun/verify?error=invalid');
  }

  try {
    const completed = await completeKinsunEmailAuth({
      challengeToken,
      verificationCode,
      password,
      ...(invitationCode ? { invitationCode } : {}),
    });
    const response = redirect(returnTo);
    clearKinsunAuthCookies(response);
    response.cookies.set(
      appSessionCookieName(),
      completed.sessionToken,
      appSessionCookieOptions(
        appSessionMaxAge(completed.idleExpiresAt, completed.absoluteExpiresAt),
      ),
    );
    return response;
  } catch (error) {
    if (error instanceof KinsunCoreAuthError && error.status === 401) {
      return redirect('/auth/kinsun/verify?error=invalid');
    }
    return redirect('/auth/kinsun/verify?error=unavailable');
  }
}
