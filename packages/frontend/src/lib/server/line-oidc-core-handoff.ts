import { logAuthDiagnostic } from './auth-diagnostics';
import type { LineOidcTransaction } from './line-oidc-transaction';

const HANDOFF_PATH = '/api/v1/internal/auth/line/handoff';
export const LINE_ONBOARDING_PATH = '/api/v1/internal/auth/line/onboarding';
const HANDOFF_TIMEOUT_MS = 10_000;
const MAX_RESPONSE_BYTES = 64 * 1024;
export const LINE_APP_SESSION_PATTERN = /^ks1_[A-Za-z0-9_-]{43}$/;
const PENDING_IDENTITY_PATTERN = /^kp1_[A-Za-z0-9_-]{43}$/;

export interface AuthenticatedLineCoreHandoff {
  status: 'AUTHENTICATED';
  sessionToken: string;
  idleExpiresAt: string;
  absoluteExpiresAt: string;
}

export interface PendingLineCoreHandoff {
  status: 'PENDING';
  pendingToken: string;
  expiresAt: string;
}

export type LineCoreHandoffResult = AuthenticatedLineCoreHandoff | PendingLineCoreHandoff;

function safeCoreBaseUrl(): URL {
  const value = process.env.CORE_API_INTERNAL_URL;
  if (!value) throw new Error('Core LINE handoff is unavailable');
  try {
    const target = new URL(value);
    if (
      target.username ||
      target.password ||
      target.search ||
      target.hash ||
      (target.protocol !== 'http:' && target.protocol !== 'https:')
    ) {
      throw new Error('invalid');
    }
    return target;
  } catch {
    throw new Error('Core LINE handoff is unavailable');
  }
}

export function lineOidcCoreTarget(path = HANDOFF_PATH): URL {
  if (path !== HANDOFF_PATH && path !== LINE_ONBOARDING_PATH) {
    throw new Error('Core LINE handoff is unavailable');
  }
  const coreBase = safeCoreBaseUrl();
  const target = new URL(path, coreBase);
  if (target.origin !== coreBase.origin || target.pathname !== path) {
    throw new Error('Core LINE handoff is unavailable');
  }
  return target;
}

export function lineOidcCoreAuthorization(): string {
  const value = process.env.LINE_OIDC_HANDOFF_SECRET;
  if (
    !value ||
    value !== value.trim() ||
    Buffer.byteLength(value, 'utf8') < 32 ||
    value.length > 512 ||
    /\s/.test(value)
  ) {
    throw new Error('Core LINE handoff is unavailable');
  }
  const forbiddenReuse = [
    process.env.LINE_LOGIN_CHANNEL_SECRET,
    process.env.LINE_OIDC_TRANSACTION_SECRET,
    process.env.LINE_LOGIN_LINK_TRANSACTION_SECRET,
    process.env.LINE_CHANNEL_SECRET,
    process.env.GOOGLE_OIDC_HANDOFF_SECRET,
    process.env.FAMILY_INVITATION_HMAC_SECRET,
  ];
  if (forbiddenReuse.some((candidate) => candidate && candidate === value)) {
    throw new Error('LINE handoff secret must be independent');
  }
  return `Bearer ${value}`;
}

function normalizedTimestamp(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 64) return null;
  return Number.isFinite(Date.parse(value)) ? value : null;
}

function parseHandoffResponse(value: unknown): LineCoreHandoffResult | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const data = (value as { data?: unknown }).data;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const payload = data as Record<string, unknown>;
  if (payload.status === 'AUTHENTICATED') {
    const idleExpiresAt = normalizedTimestamp(payload.idle_expires_at);
    const absoluteExpiresAt = normalizedTimestamp(payload.absolute_expires_at);
    if (
      typeof payload.session_token !== 'string' ||
      !LINE_APP_SESSION_PATTERN.test(payload.session_token) ||
      !idleExpiresAt ||
      !absoluteExpiresAt
    ) {
      return null;
    }
    return {
      status: 'AUTHENTICATED',
      sessionToken: payload.session_token,
      idleExpiresAt,
      absoluteExpiresAt,
    };
  }
  if (payload.status === 'PENDING') {
    const expiresAt = normalizedTimestamp(payload.expires_at);
    if (
      typeof payload.pending_token !== 'string' ||
      !PENDING_IDENTITY_PATTERN.test(payload.pending_token) ||
      !expiresAt
    ) {
      return null;
    }
    return { status: 'PENDING', pendingToken: payload.pending_token, expiresAt };
  }
  return null;
}

export async function handoffLineOidcToCore(
  idToken: string,
  transaction: LineOidcTransaction,
): Promise<LineCoreHandoffResult> {
  let response: Response;
  try {
    response = await fetch(lineOidcCoreTarget(), {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Kinsun-BFF-Authorization': lineOidcCoreAuthorization(),
      },
      body: JSON.stringify({
        id_token: idToken,
        expected_nonce: transaction.nonce,
        intent: transaction.intent,
      }),
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(HANDOFF_TIMEOUT_MS),
    });
  } catch {
    throw new Error('Core LINE handoff failed');
  }
  if (!response.ok) {
    logAuthDiagnostic('Core LINE handoff rejected', { status: response.status });
    throw new Error('Core LINE handoff failed');
  }
  const responseBody = await response.text();
  if (Buffer.byteLength(responseBody, 'utf8') > MAX_RESPONSE_BYTES) {
    throw new Error('Invalid Core LINE handoff response');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(responseBody) as unknown;
  } catch {
    throw new Error('Invalid Core LINE handoff response');
  }
  const result = parseHandoffResponse(parsed);
  if (!result) throw new Error('Invalid Core LINE handoff response');
  return result;
}
