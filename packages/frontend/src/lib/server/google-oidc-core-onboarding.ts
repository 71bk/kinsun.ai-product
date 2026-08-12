import { createHash } from 'node:crypto';
import {
  APP_SESSION_PATTERN,
  GOOGLE_ONBOARDING_PATH,
  googleOidcCoreAuthorization,
  googleOidcCoreTarget,
} from './google-oidc-core-handoff';
import type { GooglePendingOnboarding } from './google-pending-onboarding';

const REQUEST_TIMEOUT_MS = 10_000;
const MAX_RESPONSE_BYTES = 64 * 1024;

export interface CompletedGoogleCoreOnboarding {
  absoluteExpiresAt: string;
  actorId: string;
  elderId: string;
  idleExpiresAt: string;
  intent: 'ELDER' | 'FAMILY';
  sessionToken: string;
  status: 'ACTIVE' | 'REDEEMED';
  tenantId: string;
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function timestamp(value: unknown): string | null {
  return typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null;
}

function parseResponse(value: unknown): CompletedGoogleCoreOnboarding | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const data = (value as { data?: unknown }).data;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const payload = data as Record<string, unknown>;
  const idleExpiresAt = timestamp(payload.idle_expires_at);
  const absoluteExpiresAt = timestamp(payload.absolute_expires_at);
  if (
    (payload.intent !== 'ELDER' && payload.intent !== 'FAMILY') ||
    (payload.status !== 'ACTIVE' && payload.status !== 'REDEEMED') ||
    typeof payload.session_token !== 'string' ||
    !APP_SESSION_PATTERN.test(payload.session_token) ||
    typeof payload.actor_id !== 'string' ||
    !UUID_PATTERN.test(payload.actor_id) ||
    typeof payload.tenant_id !== 'string' ||
    !UUID_PATTERN.test(payload.tenant_id) ||
    typeof payload.elder_id !== 'string' ||
    !UUID_PATTERN.test(payload.elder_id) ||
    !idleExpiresAt ||
    !absoluteExpiresAt
  ) {
    return null;
  }
  return {
    absoluteExpiresAt,
    actorId: payload.actor_id,
    elderId: payload.elder_id,
    idleExpiresAt,
    intent: payload.intent,
    sessionToken: payload.session_token,
    status: payload.status,
    tenantId: payload.tenant_id,
  };
}

export async function completeGoogleOnboardingWithCore(
  pending: GooglePendingOnboarding,
  displayName?: string,
): Promise<CompletedGoogleCoreOnboarding> {
  const idempotencyKey = createHash('sha256')
    .update(`google-onboarding:${pending.pendingToken}`)
    .digest('hex');
  let response: Response;
  try {
    response = await fetch(googleOidcCoreTarget(GOOGLE_ONBOARDING_PATH), {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
        'X-Kinsun-BFF-Authorization': googleOidcCoreAuthorization(),
      },
      body: JSON.stringify({
        pending_token: pending.pendingToken,
        ...(pending.invitationCode ? { invitation_code: pending.invitationCode } : {}),
        ...(displayName ? { display_name: displayName } : {}),
      }),
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    throw new Error('Core Google onboarding failed');
  }
  if (!response.ok) throw new Error('Core Google onboarding failed');
  const body = await response.text();
  if (Buffer.byteLength(body, 'utf8') > MAX_RESPONSE_BYTES) {
    throw new Error('Invalid Core Google onboarding response');
  }
  try {
    const result = parseResponse(JSON.parse(body) as unknown);
    if (result) return result;
  } catch {
    // Fall through to one generic response error without retaining body data.
  }
  throw new Error('Invalid Core Google onboarding response');
}
