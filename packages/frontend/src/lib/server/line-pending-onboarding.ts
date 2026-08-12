import { createHmac, timingSafeEqual } from 'node:crypto';
import {
  normalizeInvitationCode,
  onboardingIntent,
  strictRelativeReturnTo,
  type OnboardingIntent,
} from './oauth-transaction';
import type { PendingLineCoreHandoff } from './line-oidc-core-handoff';
import type { LineOidcTransaction } from './line-oidc-transaction';

const DEVELOPMENT_COOKIE = 'kinsun_line_pending_onboarding';
const PRODUCTION_COOKIE = '__Host-kinsun_line_pending_onboarding';
const MAX_SERIALIZED_LENGTH = 4096;
const MAX_TTL_SECONDS = 10 * 60;
const PENDING_TOKEN_PATTERN = /^kp1_[A-Za-z0-9_-]{43}$/;

export interface LinePendingOnboarding {
  createdAt: number;
  expiresAt: number;
  intent: Exclude<OnboardingIntent, 'STAFF'>;
  invitationCode?: string;
  pendingToken: string;
  returnTo: string;
}

function signingSecret(): string {
  const secret = process.env.LINE_OIDC_TRANSACTION_SECRET;
  if (!secret || Buffer.byteLength(secret, 'utf8') < 32) {
    throw new Error('LINE pending onboarding is unavailable');
  }
  return secret;
}

function signature(payload: string): string {
  return createHmac('sha256', signingSecret()).update(payload).digest('base64url');
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left, 'ascii');
  const rightBuffer = Buffer.from(right, 'ascii');
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

export function createLinePendingOnboarding(
  handoff: PendingLineCoreHandoff,
  transaction: LineOidcTransaction,
): LinePendingOnboarding {
  if (transaction.intent === 'STAFF') throw new Error('Invalid LINE onboarding intent');
  const now = Date.now();
  const expiresAt = Date.parse(handoff.expiresAt);
  if (!Number.isFinite(expiresAt) || expiresAt <= now || expiresAt - now > MAX_TTL_SECONDS * 1000) {
    throw new Error('Invalid LINE pending expiry');
  }
  return {
    createdAt: now,
    expiresAt,
    intent: transaction.intent,
    ...(transaction.invitationCode ? { invitationCode: transaction.invitationCode } : {}),
    pendingToken: handoff.pendingToken,
    returnTo: transaction.returnTo,
  };
}

export function serializeLinePendingOnboarding(value: LinePendingOnboarding): string {
  const payload = Buffer.from(JSON.stringify(value), 'utf8').toString('base64url');
  return `${payload}.${signature(payload)}`;
}

export function parseLinePendingOnboarding(
  value: string | undefined,
): LinePendingOnboarding | null {
  if (!value || value.length > MAX_SERIALIZED_LENGTH) return null;
  const [payload, suppliedSignature, ...extra] = value.split('.');
  if (
    !payload ||
    !suppliedSignature ||
    extra.length > 0 ||
    !/^[A-Za-z0-9_-]+$/.test(payload) ||
    !/^[A-Za-z0-9_-]{43}$/.test(suppliedSignature) ||
    !safeEqual(signature(payload), suppliedSignature)
  ) {
    return null;
  }
  try {
    const parsed = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as Record<
      string,
      unknown
    >;
    const intent = onboardingIntent(parsed.intent);
    const invitationCode = normalizeInvitationCode(parsed.invitationCode);
    const returnTo =
      typeof parsed.returnTo === 'string' ? strictRelativeReturnTo(parsed.returnTo) : null;
    const now = Date.now();
    if (
      (intent !== 'ELDER' && intent !== 'FAMILY') ||
      invitationCode === null ||
      (intent !== 'FAMILY' && invitationCode !== undefined) ||
      returnTo === null ||
      returnTo !== parsed.returnTo ||
      typeof parsed.pendingToken !== 'string' ||
      !PENDING_TOKEN_PATTERN.test(parsed.pendingToken) ||
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
    return {
      createdAt: parsed.createdAt,
      expiresAt: parsed.expiresAt,
      intent,
      ...(invitationCode ? { invitationCode } : {}),
      pendingToken: parsed.pendingToken,
      returnTo,
    };
  } catch {
    return null;
  }
}

export function linePendingOnboardingCookieName(): string {
  return process.env.NODE_ENV === 'production' ? PRODUCTION_COOKIE : DEVELOPMENT_COOKIE;
}

export function linePendingOnboardingCookieOptions(maxAge = MAX_TTL_SECONDS) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge,
  };
}
