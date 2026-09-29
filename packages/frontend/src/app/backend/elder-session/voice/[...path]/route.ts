import { type NextRequest } from 'next/server';
import { assistedElderCoreRequest, noStoreCoreResponse } from '@/lib/server/assisted-elder-session-core';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { elderSessionCookieName, normalizeElderSession } from '@/lib/server/elder-session-cookie';

export const dynamic = 'force-dynamic';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  const token = normalizeElderSession(request.cookies.get(elderSessionCookieName())?.value);
  if (!token) return bffError(401, 'unauthorized', 'Elder Session required', 'ELDER_SESSION_REQUIRED');
  const { path } = await context.params;
  let suffix: string;
  if (path.length === 1 && path[0] === 'tickets') suffix = 'voice-tickets';
  else if (path.length === 2 && UUID.test(path[0]) && ['turns', 'cancel'].includes(path[1])) {
    suffix = `voice-sessions/${path[0]}/${path[1] === 'turns' ? 'companion-turns' : 'cancel'}`;
  } else return bffError(404, 'not_found', 'Resource not found', 'NOT_FOUND');
  const raw = await request.text();
  if (raw.length > 16_384) return bffError(413, 'payload_too_large', 'Request too large', 'PAYLOAD_TOO_LARGE');
  let body: Record<string, unknown> = {};
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error();
    body = parsed as Record<string, unknown>;
    const allowed = suffix === 'voice-tickets' ? ['language_preference'] : path[1] === 'turns' ? ['input_text'] : [];
    if (Object.keys(body).some((key) => !allowed.includes(key))) throw new Error();
    if (suffix === 'voice-tickets' && !['ZH_TW', 'EN_US'].includes(String(body.language_preference))) throw new Error();
    if (path[1] === 'turns' && (typeof body.input_text !== 'string' || !body.input_text.trim() || body.input_text.length > 4000)) throw new Error();
  } catch {
    return bffError(400, 'bad_request', 'Invalid voice request', 'INVALID_VOICE_REQUEST');
  }
  try {
    return noStoreCoreResponse(await assistedElderCoreRequest(
      `api/v1/assisted-elder-sessions/current/${suffix}`,
      { method: 'POST', headers: { 'Idempotency-Key': request.headers.get('idempotency-key') ?? crypto.randomUUID() }, body: JSON.stringify(body) },
      token,
    ));
  } catch {
    return bffError(502, 'bad_gateway', 'Core API is unavailable', 'CORE_API_UNAVAILABLE', true);
  }
}
