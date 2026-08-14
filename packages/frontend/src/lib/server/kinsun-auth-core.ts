import { logAuthDiagnostic } from './auth-diagnostics';

const START_PATH = '/api/v1/internal/auth/kinsun/email/start';
const COMPLETE_PATH = '/api/v1/internal/auth/kinsun/email/complete';
const PASSWORD_LOGIN_PATH = '/api/v1/internal/auth/kinsun/password/login';
const REQUEST_TIMEOUT_MS = 10_000;
const MAX_RESPONSE_BYTES = 64 * 1024;
const CHALLENGE_PATTERN = /^ke1_[A-Za-z0-9_-]{43}$/;
const APP_SESSION_PATTERN = /^ks1_[A-Za-z0-9_-]{43}$/;
const EMAIL_PATTERN =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/;

export type KinsunAuthIntent = 'ELDER' | 'FAMILY' | 'STAFF';

export interface StartedKinsunEmailAuth {
  challengeToken: string;
  expiresAt: string;
}
export interface CompletedKinsunEmailAuth {
  sessionToken: string;
  idleExpiresAt: string;
  absoluteExpiresAt: string;
}

export class KinsunCoreAuthError extends Error {
  constructor(readonly status: number) {
    super('Kinsun authentication failed');
  }
}

export function kinsunNativeAuthEnabled(): boolean {
  return process.env.KINSUN_NATIVE_AUTH_ENABLED?.trim().toLowerCase() === 'true';
}

export function normalizeKinsunEmail(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toLowerCase();
  return normalized.length >= 3 && normalized.length <= 254 && EMAIL_PATTERN.test(normalized)
    ? normalized
    : null;
}

type CoreAuthPath = typeof START_PATH | typeof COMPLETE_PATH | typeof PASSWORD_LOGIN_PATH;

function coreTarget(path: CoreAuthPath): URL {
  const value = process.env.CORE_API_INTERNAL_URL;
  if (!value) throw new Error('Kinsun authentication is unavailable');
  const base = new URL(value);
  if (
    base.username ||
    base.password ||
    base.search ||
    base.hash ||
    (base.protocol !== 'http:' && base.protocol !== 'https:')
  ) {
    throw new Error('Kinsun authentication is unavailable');
  }
  const target = new URL(path, base);
  if (target.origin !== base.origin || target.pathname !== path) {
    throw new Error('Kinsun authentication is unavailable');
  }
  return target;
}

function coreAuthorization(): string {
  const value = process.env.KINSUN_AUTH_HANDOFF_SECRET;
  if (
    !value ||
    value !== value.trim() ||
    Buffer.byteLength(value, 'utf8') < 32 ||
    value.length > 512 ||
    /\s/.test(value)
  ) {
    throw new Error('Kinsun authentication is unavailable');
  }
  const forbiddenReuse = [
    process.env.GOOGLE_OIDC_HANDOFF_SECRET,
    process.env.GOOGLE_OIDC_TRANSACTION_SECRET,
    process.env.LINE_OIDC_HANDOFF_SECRET,
    process.env.LINE_OIDC_TRANSACTION_SECRET,
    process.env.LINE_CHANNEL_SECRET,
    process.env.FAMILY_INVITATION_HMAC_SECRET,
    process.env.KINSUN_IDENTITY_HMAC_SECRET,
    process.env.KINSUN_EMAIL_CHALLENGE_HMAC_SECRET,
  ];
  if (forbiddenReuse.some((candidate) => candidate && candidate === value)) {
    throw new Error('Kinsun authentication is unavailable');
  }
  return `Bearer ${value}`;
}

function timestamp(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 64) return null;
  return Number.isFinite(Date.parse(value)) ? value : null;
}

async function postCore(path: CoreAuthPath, body: unknown) {
  let response: Response;
  try {
    response = await fetch(coreTarget(path), {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Kinsun-BFF-Authorization': coreAuthorization(),
      },
      body: JSON.stringify(body),
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    throw new KinsunCoreAuthError(503);
  }
  if (!response.ok) {
    logAuthDiagnostic('Core Kinsun authentication rejected', { status: response.status });
    throw new KinsunCoreAuthError(response.status);
  }
  const raw = await response.text();
  if (Buffer.byteLength(raw, 'utf8') > MAX_RESPONSE_BYTES) {
    throw new KinsunCoreAuthError(502);
  }
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    throw new KinsunCoreAuthError(502);
  }
}

function dataRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const data = (value as { data?: unknown }).data;
  return data && typeof data === 'object' && !Array.isArray(data)
    ? (data as Record<string, unknown>)
    : null;
}

function hasOnlyKeys(data: Record<string, unknown> | null, keys: readonly string[]): boolean {
  if (!data) return false;
  const allowed = new Set(keys);
  return Object.keys(data).every((key) => allowed.has(key));
}

export async function startKinsunEmailAuth(input: {
  email: string;
  intent: KinsunAuthIntent;
  displayName?: string;
}): Promise<StartedKinsunEmailAuth> {
  const data = dataRecord(
    await postCore(START_PATH, {
      email: input.email,
      intent: input.intent,
      ...(input.displayName ? { display_name: input.displayName } : {}),
    }),
  );
  const expiresAt = timestamp(data?.expires_at);
  if (
    !hasOnlyKeys(data, ['status', 'challenge_token', 'expires_at']) ||
    data?.status !== 'CHALLENGE_CREATED' ||
    typeof data.challenge_token !== 'string' ||
    !CHALLENGE_PATTERN.test(data.challenge_token) ||
    !expiresAt
  ) {
    throw new KinsunCoreAuthError(502);
  }
  return { challengeToken: data.challenge_token, expiresAt };
}

export async function completeKinsunEmailAuth(input: {
  challengeToken: string;
  verificationCode: string;
  password: string;
  invitationCode?: string;
}): Promise<CompletedKinsunEmailAuth> {
  const data = dataRecord(
    await postCore(COMPLETE_PATH, {
      challenge_token: input.challengeToken,
      verification_code: input.verificationCode,
      password: input.password,
      ...(input.invitationCode ? { invitation_code: input.invitationCode } : {}),
    }),
  );
  const idleExpiresAt = timestamp(data?.idle_expires_at);
  const absoluteExpiresAt = timestamp(data?.absolute_expires_at);
  if (
    !hasOnlyKeys(data, ['status', 'session_token', 'idle_expires_at', 'absolute_expires_at']) ||
    data?.status !== 'AUTHENTICATED' ||
    typeof data.session_token !== 'string' ||
    !APP_SESSION_PATTERN.test(data.session_token) ||
    !idleExpiresAt ||
    !absoluteExpiresAt
  ) {
    throw new KinsunCoreAuthError(502);
  }
  return { sessionToken: data.session_token, idleExpiresAt, absoluteExpiresAt };
}

export async function loginWithKinsunPassword(input: {
  email: string;
  password: string;
}): Promise<CompletedKinsunEmailAuth> {
  const data = dataRecord(
    await postCore(PASSWORD_LOGIN_PATH, {
      email: input.email,
      password: input.password,
    }),
  );
  const idleExpiresAt = timestamp(data?.idle_expires_at);
  const absoluteExpiresAt = timestamp(data?.absolute_expires_at);
  if (
    !hasOnlyKeys(data, ['status', 'session_token', 'idle_expires_at', 'absolute_expires_at']) ||
    data?.status !== 'AUTHENTICATED' ||
    typeof data.session_token !== 'string' ||
    !APP_SESSION_PATTERN.test(data.session_token) ||
    !idleExpiresAt ||
    !absoluteExpiresAt
  ) {
    throw new KinsunCoreAuthError(502);
  }
  return { sessionToken: data.session_token, idleExpiresAt, absoluteExpiresAt };
}
