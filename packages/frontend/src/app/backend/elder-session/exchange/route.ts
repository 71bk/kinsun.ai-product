import { type NextRequest, NextResponse } from 'next/server';
import {
  assistedElderCoreRequest,
  noStoreCoreResponse,
} from '@/lib/server/assisted-elder-session-core';
import {
  appSessionCookieName,
  appSessionCookieOptions,
} from '@/lib/server/app-session-cookie';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import {
  elderSessionCookieMaxAge,
  elderSessionCookieName,
  elderSessionCookieOptions,
  normalizeElderSession,
} from '@/lib/server/elder-session-cookie';

export const dynamic = 'force-dynamic';

const PAIRING_PATTERN = /^ep1_[A-Za-z0-9_-]{43}$/;

interface ExchangeEnvelope {
  data?: {
    assisted_session_id?: string;
    elder_id?: string;
    display_name?: string;
    preferred_name?: string | null;
    session_token?: string;
    idle_expires_at?: string;
    absolute_expires_at?: string;
  };
}
export async function POST(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  const raw = await request.text();
  if (raw.length > 1024) {
    return bffError(413, 'payload_too_large', 'Request body is too large', 'PAYLOAD_TOO_LARGE');
  }
  let pairingToken = '';
  try {
    const body = JSON.parse(raw) as { pairing_token?: unknown };
    pairingToken = typeof body.pairing_token === 'string' ? body.pairing_token : '';
  } catch {
    return bffError(400, 'bad_request', 'Invalid pairing request', 'INVALID_PAIRING_REQUEST');
  }
  if (!PAIRING_PATTERN.test(pairingToken)) {
    return bffError(400, 'bad_request', 'Invalid pairing request', 'INVALID_PAIRING_REQUEST');
  }

  let upstream: Response;
  try {
    upstream = await assistedElderCoreRequest('api/v1/assisted-elder-sessions/exchange', {
      method: 'POST',
      body: JSON.stringify({ pairing_token: pairingToken }),
    });
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

  const envelope = (await upstream.json()) as ExchangeEnvelope;
  const data = envelope.data;
  const sessionToken = normalizeElderSession(data?.session_token);
  if (
    !data?.assisted_session_id ||
    !data.elder_id ||
    !data.display_name ||
    !data.idle_expires_at ||
    !data.absolute_expires_at ||
    !sessionToken
  ) {
    return bffError(502, 'bad_gateway', 'Core API returned an invalid session', 'INVALID_CORE_RESPONSE');
  }

  let maxAge: number;
  try {
    maxAge = elderSessionCookieMaxAge(data.idle_expires_at, data.absolute_expires_at);
  } catch {
    return bffError(502, 'bad_gateway', 'Core API returned an invalid session', 'INVALID_CORE_RESPONSE');
  }
  const response = NextResponse.json({
    assisted_session_id: data.assisted_session_id,
    elder_id: data.elder_id,
    display_name: data.display_name,
    preferred_name: data.preferred_name ?? null,
    idle_expires_at: data.idle_expires_at,
    absolute_expires_at: data.absolute_expires_at,
  });
  response.cookies.set(elderSessionCookieName(), sessionToken, {
    ...elderSessionCookieOptions(maxAge),
  });
  response.cookies.set(appSessionCookieName(), '', {
    ...appSessionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}
