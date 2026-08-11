import { type NextRequest, NextResponse } from 'next/server';
import {
  accessTokenCookieName,
  isTrustedRequestOrigin,
  normalizeAccessToken,
} from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import {
  createCoreLineLinkChallenge,
  lineLinkCookieName,
  lineLinkCookieOptions,
  normalizeLineLinkToken,
} from '@/lib/server/line-account-link';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function redirect(location: string): NextResponse {
  return new NextResponse(null, {
    status: 303,
    headers: {
      'Cache-Control': 'no-store',
      Location: location,
      'Referrer-Policy': 'no-referrer',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

function clearLineLinkCookie(response: NextResponse): NextResponse {
  response.cookies.set(lineLinkCookieName(), '', {
    ...lineLinkCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return response;
}

export async function POST(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  const accessToken = normalizeAccessToken(request.cookies.get(accessTokenCookieName())?.value);
  if (!accessToken) {
    return bffError(401, 'unauthorized', 'Authentication required', 'AUTHENTICATION_REQUIRED');
  }
  const linkToken = normalizeLineLinkToken(request.cookies.get(lineLinkCookieName())?.value);
  if (!linkToken) {
    return clearLineLinkCookie(redirect('/line/account-link?error=link_expired'));
  }

  const result = await createCoreLineLinkChallenge(accessToken, linkToken);
  if (result.accountLinkUrl) {
    return clearLineLinkCookie(redirect(result.accountLinkUrl));
  }
  if (result.status === 409) {
    return clearLineLinkCookie(redirect('/line/account-link?status=already_linked'));
  }
  if (result.status === 401 || result.status === 403) {
    return bffError(401, 'unauthorized', 'Authentication required', 'AUTHENTICATION_REQUIRED');
  }
  if (result.status >= 400 && result.status < 500) {
    return clearLineLinkCookie(redirect('/line/account-link?error=link_failed'));
  }
  return redirect('/line/account-link?error=service_unavailable');
}
