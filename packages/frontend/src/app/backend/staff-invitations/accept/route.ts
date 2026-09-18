import { NextRequest, NextResponse } from 'next/server';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import {
  acceptStaffInvitation,
  INVITATION_TOKEN_PATTERN,
  kinsunNativeAuthEnabled,
  normalizeKinsunEmail,
} from '@/lib/server/kinsun-auth-core';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const MAX_BODY_BYTES = 4096;

/**
 * Redeems a workforce invitation. The credential reaches this route in a JSON
 * body from the same origin, never as a query parameter — a URL would end up in
 * server logs, the Referer header and browser history.
 *
 * Every rejection collapses into one 400. Core already refuses to distinguish a
 * spent credential from an expired one, a revoked one, or an email that does
 * not match the invitation; re-deriving that distinction here from status codes
 * would hand an attacker the oracle Core denies them.
 */
export async function POST(request: NextRequest): Promise<Response> {
  if (!kinsunNativeAuthEnabled()) return new Response(null, { status: 404 });
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }

  const raw = await request.text();
  if (Buffer.byteLength(raw, 'utf8') > MAX_BODY_BYTES) {
    return bffError(413, 'payload_too_large', 'Request body is too large', 'PAYLOAD_TOO_LARGE');
  }

  let body: { email?: unknown; password?: unknown; invitation_token?: unknown };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return bffError(400, 'bad_request', 'Invitation cannot be accepted', 'INVITATION_REJECTED');
    }
    body = parsed as typeof body;
  } catch {
    return bffError(400, 'bad_request', 'Invitation cannot be accepted', 'INVITATION_REJECTED');
  }

  const email = normalizeKinsunEmail(body.email);
  const password = typeof body.password === 'string' ? body.password : '';
  const invitationToken = typeof body.invitation_token === 'string' ? body.invitation_token : '';

  if (
    !email ||
    !INVITATION_TOKEN_PATTERN.test(invitationToken) ||
    password.length < 12 ||
    password.length > 128 ||
    Buffer.byteLength(password, 'utf8') > 1024 ||
    password.includes('\0')
  ) {
    return bffError(400, 'bad_request', 'Invitation cannot be accepted', 'INVITATION_REJECTED');
  }

  try {
    await acceptStaffInvitation({ email, password, invitationToken });
  } catch {
    return bffError(400, 'bad_request', 'Invitation cannot be accepted', 'INVITATION_REJECTED');
  }

  const response = NextResponse.json({ status: 'ACTIVATED' });
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}
