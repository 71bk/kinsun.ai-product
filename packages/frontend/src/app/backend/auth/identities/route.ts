import { NextRequest } from 'next/server';
import { accessTokenCookieName } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { CognitoIdentityError, getSignInMethodStatus } from '@/lib/server/cognito-identities';
import { lineLoginEnabled } from '@/lib/server/line-login-oauth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(request: NextRequest): Promise<Response> {
  try {
    const status = await getSignInMethodStatus(request.cookies.get(accessTokenCookieName())?.value);
    return Response.json(
      {
        data: {
          googleLinked: status.googleLinked,
          lineLinked: status.lineLinked,
          lineLoginEnabled: lineLoginEnabled(),
        },
        meta: {
          correlation_id: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          schema_version: '1.0',
        },
      },
      {
        headers: {
          'Cache-Control': 'no-store',
          'X-Content-Type-Options': 'nosniff',
        },
      },
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
