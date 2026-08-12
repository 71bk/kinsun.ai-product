import { NextRequest } from 'next/server';
import { appSessionCookieName, normalizeAppSession } from '@/lib/server/app-session-cookie';
import { accessTokenCookieName } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { CognitoIdentityError, getSignInMethodStatus } from '@/lib/server/cognito-identities';
import { getLineIdentityMethodStatus } from '@/lib/server/line-account-link-core';
import { lineDirectOidcEnabled, lineLoginEnabled } from '@/lib/server/line-login-oauth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(request: NextRequest): Promise<Response> {
  const appSession = normalizeAppSession(request.cookies.get(appSessionCookieName())?.value);
  if (!appSession) {
    try {
      const legacy = await getSignInMethodStatus(
        request.cookies.get(accessTokenCookieName())?.value,
      );
      return Response.json(
        {
          data: {
            googleLinked: legacy.googleLinked,
            lineLinked: legacy.lineLinked,
            lineLoginEnabled: lineLoginEnabled(),
            recentlyAuthenticated: true,
          },
        },
        { headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } },
      );
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
        'Sign-in methods are temporarily unavailable',
        'IDENTITY_PROVIDER_UNAVAILABLE',
        true,
      );
    }
  }
  try {
    const status = await getLineIdentityMethodStatus(appSession);
    return Response.json(
      {
        data: {
          ...status,
          lineLoginEnabled: lineDirectOidcEnabled(),
        },
        meta: {
          correlation_id: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          schema_version: '1.0',
        },
      },
      { headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } },
    );
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
      'Sign-in methods are temporarily unavailable',
      'IDENTITY_PROVIDER_UNAVAILABLE',
      true,
    );
  }
}
