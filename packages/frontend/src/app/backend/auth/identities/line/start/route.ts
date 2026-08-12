import { NextRequest, NextResponse } from 'next/server';
import { appSessionCookieName, normalizeAppSession } from '@/lib/server/app-session-cookie';
import { accessTokenCookieName, isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { CognitoIdentityError, getLineLoginLinkDestination } from '@/lib/server/cognito-identities';
import { getLineIdentityMethodStatus } from '@/lib/server/line-account-link-core';
import {
  createLineAccountLinkTransaction,
  lineAccountLinkCookieName,
  lineAccountLinkCookieOptions,
  serializeLineAccountLinkTransaction,
} from '@/lib/server/line-account-link-transaction';
import {
  createLineLoginLinkTransaction,
  lineLoginLinkCookieName,
  lineLoginLinkCookieOptions,
  serializeLineLoginLinkTransaction,
} from '@/lib/server/line-login-link-transaction';
import {
  buildLineLoginLinkAuthorizationUrl,
  getLineLoginOAuthConfig,
  lineDirectOidcEnabled,
  lineLoginEnabled,
} from '@/lib/server/line-login-oauth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

function accountRedirect(status: string): NextResponse {
  return noStore(
    new NextResponse(null, {
      status: 303,
      headers: { Location: `/account/sign-in-methods?status=${status}` },
    }),
  );
}

export async function POST(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  if (!lineDirectOidcEnabled() && !lineLoginEnabled()) {
    return bffError(404, 'not_found', 'LINE Login is unavailable', 'LINE_LOGIN_DISABLED');
  }
  const appSession = normalizeAppSession(request.cookies.get(appSessionCookieName())?.value);
  if (!appSession) {
    if (!lineLoginEnabled()) {
      return bffError(
        401,
        'authentication_required',
        'Authentication required',
        'AUTHENTICATION_REQUIRED',
      );
    }
    try {
      const destination = await getLineLoginLinkDestination(
        request.cookies.get(accessTokenCookieName())?.value,
      );
      if (!destination.googleLinked) {
        return bffError(
          409,
          'conflict',
          'Google sign-in is required before linking LINE',
          'GOOGLE_IDENTITY_REQUIRED',
        );
      }
      if (destination.lineLinked) return accountRedirect('already_linked');
      const transaction = createLineLoginLinkTransaction(destination.cognitoUsername);
      const response = noStore(
        NextResponse.redirect(
          buildLineLoginLinkAuthorizationUrl(getLineLoginOAuthConfig(), transaction),
          { status: 303 },
        ),
      );
      response.cookies.set(
        lineLoginLinkCookieName(),
        serializeLineLoginLinkTransaction(transaction),
        lineLoginLinkCookieOptions(),
      );
      return response;
    } catch (error) {
      if (error instanceof CognitoIdentityError && error.reason === 'AUTHENTICATION_REQUIRED') {
        return bffError(
          401,
          'authentication_required',
          'Authentication required',
          'AUTHENTICATION_REQUIRED',
        );
      }
      return bffError(
        503,
        'service_unavailable',
        'LINE linking is temporarily unavailable',
        'LINE_LINK_UNAVAILABLE',
        true,
      );
    }
  }
  if (!lineDirectOidcEnabled()) {
    return bffError(404, 'not_found', 'LINE Login is unavailable', 'LINE_LOGIN_DISABLED');
  }

  try {
    const status = await getLineIdentityMethodStatus(appSession);
    if (!status.googleLinked) {
      return bffError(
        409,
        'conflict',
        'Google sign-in is required before linking LINE',
        'GOOGLE_IDENTITY_REQUIRED',
      );
    }
    if (!status.recentlyAuthenticated) {
      return bffError(
        401,
        'authentication_required',
        'Recent authentication is required',
        'RECENT_AUTHENTICATION_REQUIRED',
      );
    }
    if (status.lineLinked) return accountRedirect('already_linked');

    const transaction = createLineAccountLinkTransaction(appSession);
    const config = getLineLoginOAuthConfig('direct-link');
    const response = noStore(
      NextResponse.redirect(buildLineLoginLinkAuthorizationUrl(config, transaction), {
        status: 303,
      }),
    );
    response.cookies.set(
      lineAccountLinkCookieName(),
      serializeLineAccountLinkTransaction(transaction),
      lineAccountLinkCookieOptions(),
    );
    return response;
  } catch (error) {
    if (error instanceof Error && error.message === 'Authentication required') {
      return bffError(
        401,
        'authentication_required',
        'Authentication required',
        'AUTHENTICATION_REQUIRED',
      );
    }
    return bffError(
      503,
      'service_unavailable',
      'LINE linking is temporarily unavailable',
      'LINE_LINK_UNAVAILABLE',
      true,
    );
  }
}
