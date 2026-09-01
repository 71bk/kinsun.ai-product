import { type NextRequest, NextResponse } from 'next/server';
import {
  assistedElderCoreRequest,
  noStoreCoreResponse,
} from '@/lib/server/assisted-elder-session-core';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import {
  elderSessionCookieName,
  elderSessionCookieOptions,
  normalizeElderSession,
} from '@/lib/server/elder-session-cookie';

export const dynamic = 'force-dynamic';

function credential(request: NextRequest): string | null {
  return normalizeElderSession(request.cookies.get(elderSessionCookieName())?.value);
}
export async function GET(request: NextRequest): Promise<Response> {
  const token = credential(request);
  if (!token) {
    return bffError(401, 'unauthorized', 'Elder Session required', 'ELDER_SESSION_REQUIRED');
  }
  try {
    return noStoreCoreResponse(
      await assistedElderCoreRequest(
        'api/v1/assisted-elder-sessions/current',
        { method: 'GET' },
        token,
      ),
    );
  } catch {
    return bffError(
      502,
      'bad_gateway',
      'Core API is unavailable',
      'CORE_API_UNAVAILABLE',
      true,
    );
  }
}

export async function DELETE(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  const token = credential(request);
  if (!token) {
    return bffError(401, 'unauthorized', 'Elder Session required', 'ELDER_SESSION_REQUIRED');
  }
  let upstream: Response;
  try {
    upstream = await assistedElderCoreRequest(
      'api/v1/assisted-elder-sessions/current/end',
      { method: 'POST' },
      token,
    );
  } catch {
    return bffError(
      502,
      'bad_gateway',
      'Core API is unavailable',
      'CORE_API_UNAVAILABLE',
      true,
    );
  }
  if (!upstream.ok) return noStoreCoreResponse(upstream);
  const response = NextResponse.json({ status: 'ENDED' });
  response.cookies.set(elderSessionCookieName(), '', {
    ...elderSessionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  response.headers.set('Cache-Control', 'no-store');
  return response;
}
