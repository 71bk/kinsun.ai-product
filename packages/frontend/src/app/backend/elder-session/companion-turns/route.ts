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

export async function POST(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  const token = normalizeElderSession(request.cookies.get(elderSessionCookieName())?.value);
  if (!token) {
    return bffError(401, 'unauthorized', 'Elder Session required', 'ELDER_SESSION_REQUIRED');
  }
  const raw = await request.text();
  if (raw.length > 16_384) {
    return bffError(413, 'payload_too_large', 'Request body is too large', 'PAYLOAD_TOO_LARGE');
  }
  let inputText = '';
  try {
    const body = JSON.parse(raw) as { input_text?: unknown };
    inputText = typeof body.input_text === 'string' ? body.input_text.trim() : '';
  } catch {
    return bffError(400, 'bad_request', 'Invalid companion request', 'INVALID_COMPANION_REQUEST');
  }
  if (!inputText || inputText.length > 4000) {
    return bffError(400, 'bad_request', 'Invalid companion request', 'INVALID_COMPANION_REQUEST');
  }
  const idempotencyKey = request.headers.get('idempotency-key') ?? `elder-turn-${crypto.randomUUID()}`;
  try {
    return noStoreCoreResponse(
      await assistedElderCoreRequest(
        'api/v1/assisted-elder-sessions/current/companion-turns',
        {
          method: 'POST',
          headers: { 'Idempotency-Key': idempotencyKey },
          body: JSON.stringify({ input_text: inputText }),
        },
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
