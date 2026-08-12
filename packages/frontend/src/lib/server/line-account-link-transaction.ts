import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { normalizeAppSession } from './app-session-cookie';
import { lineLoginCodeChallenge } from './line-login-link-transaction';

const DEVELOPMENT_COOKIE = 'kinsun_line_account_link';
const PRODUCTION_COOKIE = '__Host-kinsun_line_account_link';
const TTL_SECONDS = 10 * 60;
const RANDOM_PATTERN = /^[A-Za-z0-9_-]{43,128}$/;
const CODE_VERIFIER_PATTERN = /^[A-Za-z0-9._~-]{43,128}$/;
const DIGEST_PATTERN = /^[0-9a-f]{64}$/;

export interface LineAccountLinkTransaction {
  codeVerifier: string;
  createdAt: number;
  nonce: string;
  sessionDigest: string;
  state: string;
}

function secret(): string {
  const value = process.env.LINE_OIDC_TRANSACTION_SECRET;
  if (!value || Buffer.byteLength(value, 'utf8') < 32) {
    throw new Error('LINE account linking is unavailable');
  }
  return value;
}

function sign(payload: string): string {
  return createHmac('sha256', secret()).update(`account-link:${payload}`).digest('base64url');
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left, 'ascii');
  const rightBuffer = Buffer.from(right, 'ascii');
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

export function appSessionFingerprint(rawToken: unknown): string | null {
  const token = normalizeAppSession(rawToken);
  return token ? createHash('sha256').update(token, 'ascii').digest('hex') : null;
}

export function createLineAccountLinkTransaction(
  appSessionToken: string,
): LineAccountLinkTransaction {
  const sessionDigest = appSessionFingerprint(appSessionToken);
  if (!sessionDigest) throw new Error('Authentication required');
  const random = () => randomBytes(32).toString('base64url');
  return {
    codeVerifier: random(),
    createdAt: Date.now(),
    nonce: random(),
    sessionDigest,
    state: random(),
  };
}

export function serializeLineAccountLinkTransaction(
  transaction: LineAccountLinkTransaction,
): string {
  const payload = Buffer.from(JSON.stringify(transaction), 'utf8').toString('base64url');
  return `${payload}.${sign(payload)}`;
}

export function parseLineAccountLinkTransaction(
  value: string | undefined,
): LineAccountLinkTransaction | null {
  if (!value || value.length > 4096) return null;
  const [payload, supplied, ...extra] = value.split('.');
  if (
    !payload ||
    !supplied ||
    extra.length > 0 ||
    !/^[A-Za-z0-9_-]+$/.test(payload) ||
    !/^[A-Za-z0-9_-]{43}$/.test(supplied) ||
    !safeEqual(sign(payload), supplied)
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
      typeof parsed.createdAt !== 'number' ||
      !Number.isSafeInteger(parsed.createdAt) ||
      parsed.createdAt > now ||
      now - parsed.createdAt > TTL_SECONDS * 1000 ||
      typeof parsed.codeVerifier !== 'string' ||
      !CODE_VERIFIER_PATTERN.test(parsed.codeVerifier) ||
      typeof parsed.nonce !== 'string' ||
      !RANDOM_PATTERN.test(parsed.nonce) ||
      typeof parsed.state !== 'string' ||
      !RANDOM_PATTERN.test(parsed.state) ||
      typeof parsed.sessionDigest !== 'string' ||
      !DIGEST_PATTERN.test(parsed.sessionDigest)
    ) {
      return null;
    }
    return parsed as unknown as LineAccountLinkTransaction;
  } catch {
    return null;
  }
}

export function lineAccountLinkOwnsSession(
  transaction: LineAccountLinkTransaction,
  rawAppSessionToken: unknown,
): boolean {
  const current = appSessionFingerprint(rawAppSessionToken);
  return current !== null && safeEqual(transaction.sessionDigest, current);
}

export function lineAccountLinkStateMatches(
  transaction: LineAccountLinkTransaction,
  suppliedState: string | null,
): boolean {
  return suppliedState !== null && safeEqual(transaction.state, suppliedState);
}

export function lineAccountLinkCodeChallenge(transaction: LineAccountLinkTransaction): string {
  return lineLoginCodeChallenge(transaction);
}

export function lineAccountLinkCookieName(): string {
  return process.env.NODE_ENV === 'production' ? PRODUCTION_COOKIE : DEVELOPMENT_COOKIE;
}

export function lineAccountLinkCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: TTL_SECONDS,
  };
}
