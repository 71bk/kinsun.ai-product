import { createHmac, timingSafeEqual } from 'node:crypto';

const DEVELOPMENT_COOKIE = 'kinsun_line_account_merge';
const PRODUCTION_COOKIE = '__Host-kinsun_line_account_merge';
const MERGE_TOKEN_PATTERN = /^km1_[A-Za-z0-9_-]{43}$/;
const MAX_TTL_SECONDS = 15 * 60;

export interface PendingLineAccountMerge {
  createdAt: number;
  expiresAt: number;
  mergeToken: string;
}

function secret(): string {
  const value = process.env.LINE_OIDC_TRANSACTION_SECRET;
  if (!value || Buffer.byteLength(value, 'utf8') < 32) {
    throw new Error('LINE account merge is unavailable');
  }
  return value;
}

function signature(payload: string): string {
  return createHmac('sha256', secret()).update(`account-merge:${payload}`).digest('base64url');
}

function safeEqual(left: string, right: string): boolean {
  const a = Buffer.from(left, 'ascii');
  const b = Buffer.from(right, 'ascii');
  return a.length === b.length && timingSafeEqual(a, b);
}

export function createPendingLineAccountMerge(
  mergeToken: string,
  expiresAtValue: string,
): PendingLineAccountMerge {
  const now = Date.now();
  const expiresAt = Date.parse(expiresAtValue);
  if (
    !MERGE_TOKEN_PATTERN.test(mergeToken) ||
    !Number.isFinite(expiresAt) ||
    expiresAt <= now ||
    expiresAt - now > MAX_TTL_SECONDS * 1000
  ) {
    throw new Error('Invalid LINE account merge');
  }
  return { createdAt: now, expiresAt, mergeToken };
}

export function serializePendingLineAccountMerge(value: PendingLineAccountMerge): string {
  const payload = Buffer.from(JSON.stringify(value), 'utf8').toString('base64url');
  return `${payload}.${signature(payload)}`;
}

export function parsePendingLineAccountMerge(
  value: string | undefined,
): PendingLineAccountMerge | null {
  if (!value || value.length > 2048) return null;
  const [payload, supplied, ...extra] = value.split('.');
  if (
    !payload ||
    !supplied ||
    extra.length > 0 ||
    !/^[A-Za-z0-9_-]+$/.test(payload) ||
    !/^[A-Za-z0-9_-]{43}$/.test(supplied) ||
    !safeEqual(signature(payload), supplied)
  ) {
    return null;
  }
  try {
    const parsed = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as Record<
      string,
      unknown
    >;
    const now = Date.now();
    if (
      typeof parsed.mergeToken !== 'string' ||
      !MERGE_TOKEN_PATTERN.test(parsed.mergeToken) ||
      typeof parsed.createdAt !== 'number' ||
      !Number.isSafeInteger(parsed.createdAt) ||
      parsed.createdAt > now ||
      typeof parsed.expiresAt !== 'number' ||
      !Number.isSafeInteger(parsed.expiresAt) ||
      parsed.expiresAt <= now ||
      parsed.expiresAt - parsed.createdAt > MAX_TTL_SECONDS * 1000
    ) {
      return null;
    }
    return parsed as unknown as PendingLineAccountMerge;
  } catch {
    return null;
  }
}

export function lineAccountMergeCookieName(): string {
  return process.env.NODE_ENV === 'production' ? PRODUCTION_COOKIE : DEVELOPMENT_COOKIE;
}

export function lineAccountMergeCookieOptions(maxAge = MAX_TTL_SECONDS) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge,
  };
}
