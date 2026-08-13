import { type NextRequest, NextResponse } from 'next/server';
import {
  appSessionCookieName,
  appSessionCookieOptions,
  normalizeAppSession,
} from '@/lib/server/app-session-cookie';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { revokeCoreAppSession } from '@/lib/server/core-app-session';

export const dynamic = 'force-dynamic';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

export function GET(request: NextRequest): Response {
  const credential = normalizeAppSession(request.cookies.get(appSessionCookieName())?.value);
  return noStore(NextResponse.json({ credential_present: credential !== null }));
}

export async function DELETE(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }

  const appSession = normalizeAppSession(request.cookies.get(appSessionCookieName())?.value);
  if (appSession !== null) {
    try {
      await revokeCoreAppSession(appSession);
    } catch {
      return bffError(
        503,
        'service_unavailable',
        'Sign-out is temporarily unavailable',
        'APP_SESSION_LOGOUT_UNAVAILABLE',
        true,
      );
    }
  }
  const response = noStore(NextResponse.json({ credential_present: false }));
  response.cookies.set(appSessionCookieName(), '', {
    ...appSessionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return response;
}
