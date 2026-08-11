import { NextRequest, NextResponse } from 'next/server';
import { accessTokenCookieName, isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { CognitoIdentityError, getLineLoginLinkDestination } from '@/lib/server/cognito-identities';
import {
  createLineLoginLinkTransaction,
  lineLoginLinkCookieName,
  lineLoginLinkCookieOptions,
  serializeLineLoginLinkTransaction,
} from '@/lib/server/line-login-link-transaction';
import {
  buildLineLoginLinkAuthorizationUrl,
  getLineLoginOAuthConfig,
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
  if (!lineLoginEnabled()) {
    return bffError(404, 'not_found', 'LINE Login is unavailable', 'LINE_LOGIN_DISABLED');
  }

  try {
    const accessToken = request.cookies.get(accessTokenCookieName())?.value;
    const destination = await getLineLoginLinkDestination(accessToken);
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
    const config = getLineLoginOAuthConfig();
    const response = noStore(
      NextResponse.redirect(buildLineLoginLinkAuthorizationUrl(config, transaction), {
        status: 303,
      }),
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
