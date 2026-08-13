import { NextRequest } from 'next/server';
import { appSessionCookieName, normalizeAppSession } from '@/lib/server/app-session-cookie';
import { bffError } from '@/lib/server/bff-response';
import { getLineIdentityMethodStatus } from '@/lib/server/line-account-link-core';
import { lineDirectOidcEnabled } from '@/lib/server/line-login-oauth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(request: NextRequest): Promise<Response> {
  const appSession = normalizeAppSession(request.cookies.get(appSessionCookieName())?.value);
  if (!appSession) {
    return bffError(
      401,
      'authentication_required',
      'Authentication required',
      'AUTHENTICATION_REQUIRED',
    );
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
