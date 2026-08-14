import { NextRequest, NextResponse } from 'next/server';
import {
  appSessionCookieName,
  appSessionCookieOptions,
  appSessionMaxAge,
} from '@/lib/server/app-session-cookie';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import {
  KinsunCoreAuthError,
  kinsunNativeAuthEnabled,
  loginWithKinsunPassword,
  normalizeKinsunEmail,
} from '@/lib/server/kinsun-auth-core';
import { strictRelativeReturnTo } from '@/lib/server/oauth-transaction';

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
  const email = normalizeKinsunEmail(form.get('email'));
  const password = typeof form.get('password') === 'string' ? String(form.get('password')) : '';
  const returnTo = strictRelativeReturnTo(
    typeof form.get('returnTo') === 'string' ? String(form.get('returnTo')) : null,
  );
  if (
    !returnTo ||
    !email ||
    password.length < 12 ||
    password.length > 128 ||
    Buffer.byteLength(password, 'utf8') > 1024 ||
    password.includes('\0')
  ) {
    return redirect('/sign-in?error=invalid_credentials');
  }

  try {
    const completed = await loginWithKinsunPassword({ email, password });
    const response = redirect(returnTo);
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
      return redirect('/sign-in?error=invalid_credentials');
    }
    return redirect('/sign-in?error=auth_unavailable');
  }
}
