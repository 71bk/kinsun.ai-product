import { normalizeAppSession } from './app-session-cookie';
import { lineOidcCoreAuthorization, lineOidcCoreTarget } from './line-oidc-core-handoff';

const STATUS_PATH = '/api/v1/internal/auth/line/status';
const LINK_PATH = '/api/v1/internal/auth/line/link';
const MERGE_CONFIRM_PATH = '/api/v1/internal/auth/line/merge/confirm';
const TIMEOUT_MS = 10_000;
const MAX_RESPONSE_BYTES = 64 * 1024;
const SESSION_PATTERN = /^ks1_[A-Za-z0-9_-]{43}$/;
const MERGE_PATTERN = /^km1_[A-Za-z0-9_-]{43}$/;

export interface LineIdentityMethodStatus {
  googleLinked: boolean;
  lineLinked: boolean;
  recentlyAuthenticated: boolean;
}

export type LinkLineIdentityResult =
  | { status: 'LINKED' | 'ALREADY_LINKED' }
  | { status: 'MERGE_REQUIRED'; mergeToken: string; expiresAt: string }
  | { status: 'MANUAL_REVIEW_REQUIRED' };

export type ConfirmLineMergeResult =
  | {
      status: 'MERGED';
      sessionToken: string;
      idleExpiresAt: string;
      absoluteExpiresAt: string;
    }
  | { status: 'MANUAL_REVIEW_REQUIRED' };

function target(path: string): URL {
  if (![STATUS_PATH, LINK_PATH, MERGE_CONFIRM_PATH].includes(path)) {
    throw new Error('Core LINE account linking is unavailable');
  }
  // Reuse the strict Core origin parser from the handoff module, then replace
  // only with an allowlisted fixed path.
  const handoff = lineOidcCoreTarget();
  const value = new URL(path, handoff.origin);
  if (value.origin !== handoff.origin || value.pathname !== path) {
    throw new Error('Core LINE account linking is unavailable');
  }
  return value;
}

async function requestCore(
  path: string,
  appSession: string,
  body?: Record<string, string>,
): Promise<Record<string, unknown>> {
  const token = normalizeAppSession(appSession);
  if (!token) throw new Error('Authentication required');
  const response = await fetch(target(path), {
    method: body ? 'POST' : 'GET',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Kinsun-BFF-Authorization': lineOidcCoreAuthorization(),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
    cache: 'no-store',
    redirect: 'error',
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok)
    throw new Error(response.status === 401 ? 'Authentication required' : 'Core rejected');
  const raw = await response.text();
  if (Buffer.byteLength(raw, 'utf8') > MAX_RESPONSE_BYTES) throw new Error('Invalid Core response');
  const parsed = JSON.parse(raw) as { data?: unknown };
  if (!parsed.data || typeof parsed.data !== 'object' || Array.isArray(parsed.data)) {
    throw new Error('Invalid Core response');
  }
  return parsed.data as Record<string, unknown>;
}

function timestamp(value: unknown): string | null {
  return typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null;
}

export async function getLineIdentityMethodStatus(
  appSession: string,
): Promise<LineIdentityMethodStatus> {
  const data = await requestCore(STATUS_PATH, appSession);
  if (
    typeof data.google_linked !== 'boolean' ||
    typeof data.line_linked !== 'boolean' ||
    typeof data.recently_authenticated !== 'boolean'
  ) {
    throw new Error('Invalid Core response');
  }
  return {
    googleLinked: data.google_linked,
    lineLinked: data.line_linked,
    recentlyAuthenticated: data.recently_authenticated,
  };
}

export async function linkLineIdentityWithCore(
  appSession: string,
  idToken: string,
  expectedNonce: string,
): Promise<LinkLineIdentityResult> {
  const data = await requestCore(LINK_PATH, appSession, {
    id_token: idToken,
    expected_nonce: expectedNonce,
  });
  if (data.status === 'LINKED' || data.status === 'ALREADY_LINKED') {
    return { status: data.status };
  }
  if (data.status === 'MANUAL_REVIEW_REQUIRED') return { status: data.status };
  const expiresAt = timestamp(data.expires_at);
  if (
    data.status === 'MERGE_REQUIRED' &&
    typeof data.merge_token === 'string' &&
    MERGE_PATTERN.test(data.merge_token) &&
    expiresAt
  ) {
    return { status: data.status, mergeToken: data.merge_token, expiresAt };
  }
  throw new Error('Invalid Core response');
}

export async function confirmLineAccountMergeWithCore(
  appSession: string,
  mergeToken: string,
): Promise<ConfirmLineMergeResult> {
  const data = await requestCore(MERGE_CONFIRM_PATH, appSession, { merge_token: mergeToken });
  if (data.status === 'MANUAL_REVIEW_REQUIRED') return { status: data.status };
  const idleExpiresAt = timestamp(data.idle_expires_at);
  const absoluteExpiresAt = timestamp(data.absolute_expires_at);
  if (
    data.status === 'MERGED' &&
    typeof data.session_token === 'string' &&
    SESSION_PATTERN.test(data.session_token) &&
    idleExpiresAt &&
    absoluteExpiresAt
  ) {
    return {
      status: data.status,
      sessionToken: data.session_token,
      idleExpiresAt,
      absoluteExpiresAt,
    };
  }
  throw new Error('Invalid Core response');
}
