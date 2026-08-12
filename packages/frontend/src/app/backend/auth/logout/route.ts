import { NextRequest, NextResponse } from 'next/server';
import { appSessionCookieName, appSessionCookieOptions } from '@/lib/server/app-session-cookie';
import {
  accessTokenCookieName,
  accessTokenCookieOptions,
  isTrustedRequestOrigin,
} from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { buildCognitoLogoutUrl, getCognitoOAuthConfig } from '@/lib/server/cognito-oauth';
import { revokeCoreAppSession } from '@/lib/server/core-app-session';
import {
  googlePendingOnboardingCookieName,
  googlePendingOnboardingCookieOptions,
} from '@/lib/server/google-pending-onboarding';
import {
  googleOidcTransactionCookieName,
  googleOidcTransactionCookieOptions,
} from '@/lib/server/google-oidc-transaction';
import {
  oauthTransactionCookieName,
  oauthTransactionCookieOptions,
} from '@/lib/server/oauth-transaction';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

export async function POST(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }

  const appSession = request.cookies.get(appSessionCookieName())?.value;
  let response: NextResponse;
  if (appSession !== undefined) {
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
    response = new NextResponse(null, { status: 303, headers: { Location: '/sign-in' } });
  } else {
    try {
      response = NextResponse.redirect(buildCognitoLogoutUrl(getCognitoOAuthConfig()), {
        status: 303,
      });
    } catch {
      response = new NextResponse(null, { status: 303, headers: { Location: '/sign-in' } });
    }
  }
  response.cookies.set(appSessionCookieName(), '', {
    ...appSessionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  response.cookies.set(accessTokenCookieName(), '', {
    ...accessTokenCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  response.cookies.set(oauthTransactionCookieName(), '', {
    ...oauthTransactionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  response.cookies.set(googleOidcTransactionCookieName(), '', {
    ...googleOidcTransactionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  response.cookies.set(googlePendingOnboardingCookieName(), '', {
    ...googlePendingOnboardingCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return noStore(response);
}
