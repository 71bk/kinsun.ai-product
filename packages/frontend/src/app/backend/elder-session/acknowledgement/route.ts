import { type NextRequest } from 'next/server';
import {
  assistedElderCoreRequest,
  noStoreCoreResponse,
} from '@/lib/server/assisted-elder-session-core';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import {
  elderSessionCookieName,
  normalizeElderSession,
} from '@/lib/server/elder-session-cookie';

export const dynamic = 'force-dynamic';

function credential(request: NextRequest): string | null {
  return normalizeElderSession(request.cookies.get(elderSessionCookieName())?.value);
}

function idempotencyKey(request: NextRequest, prefix: string): string {
  return request.headers.get('idempotency-key') ?? `${prefix}-${crypto.randomUUID()}`;
}

async function forward(
  request: NextRequest,
  path: string,
  init: RequestInit,
): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  const token = credential(request);
  if (!token) {
    return bffError(401, 'unauthorized', 'Elder Session required', 'ELDER_SESSION_REQUIRED');
  }
  try {
    return noStoreCoreResponse(await assistedElderCoreRequest(path, init, token));
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

export function POST(request: NextRequest): Promise<Response> {
  return forward(
    request,
    'api/v1/assisted-elder-sessions/current/first-use-acknowledgement',
    {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey(request, 'elder-ack') },
      body: JSON.stringify({ acknowledged: true }),
    },
  );
}

export function DELETE(request: NextRequest): Promise<Response> {
  return forward(
    request,
    'api/v1/assisted-elder-sessions/current/first-use-acknowledgement/revoke',
    {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey(request, 'elder-ack-revoke') },
    },
  );
}
