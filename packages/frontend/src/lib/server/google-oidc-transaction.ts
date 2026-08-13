import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import {
  normalizeInvitationCode,
  onboardingIntent,
  strictRelativeReturnTo,
  type OnboardingIntent,
} from './oauth-transaction';

const DEVELOPMENT_COOKIE = 'kinsun_google_oidc_transaction';
const PRODUCTION_COOKIE = '__Host-kinsun_google_oidc_transaction';
const TRANSACTION_TTL_SECONDS = 10 * 60;
const MAX_SERIALIZED_LENGTH = 4096;
const RANDOM_VALUE_PATTERN = /^[A-Za-z0-9_-]{43,128}$/;
const CODE_VERIFIER_PATTERN = /^[A-Za-z0-9._~-]{43,128}$/;

export interface GoogleOidcTransaction {
  codeVerifier: string;
  createdAt: number;
  intent: OnboardingIntent;
  invitationCode?: string;
  nonce: string;
  returnTo: string;
  state: string;
}

function base64Url(value: Buffer): string {
  return value.toString('base64url');
}

function randomValue(): string {
  return base64Url(randomBytes(32));
}

function signingSecret(): string {
  const secret = process.env.GOOGLE_OIDC_TRANSACTION_SECRET;
  if (!secret || Buffer.byteLength(secret, 'utf8') < 32) {
    throw new Error('Google OIDC transaction signing secret is unavailable');
  }

  const forbiddenReuse = [
    process.env.GOOGLE_OIDC_CLIENT_SECRET,
    process.env.LINE_LOGIN_CHANNEL_SECRET,
    process.env.LINE_CHANNEL_SECRET,
    process.env.FAMILY_INVITATION_HMAC_SECRET,
  ];
  if (forbiddenReuse.some((value) => value && value === secret)) {
    throw new Error('Google OIDC transaction signing secret must be independent');
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

export function createGoogleOidcTransaction(
  returnTo: string,
  intent: OnboardingIntent,
  invitationCode?: string,
): GoogleOidcTransaction {
  const normalizedReturnTo = strictRelativeReturnTo(returnTo);
  const normalizedInvitationCode = normalizeInvitationCode(invitationCode);
  if (
    normalizedReturnTo === null ||
    normalizedInvitationCode === null ||
    (intent !== 'FAMILY' && normalizedInvitationCode !== undefined)
  ) {
    throw new Error('Invalid Google OIDC transaction input');
  }

  return {
    codeVerifier: randomValue(),
    createdAt: Date.now(),
    intent,
    ...(normalizedInvitationCode ? { invitationCode: normalizedInvitationCode } : {}),
    nonce: randomValue(),
    returnTo: normalizedReturnTo,
    state: randomValue(),
  };
}

export function serializeGoogleOidcTransaction(transaction: GoogleOidcTransaction): string {
  const payload = base64Url(Buffer.from(JSON.stringify(transaction), 'utf8'));
  return `${payload}.${signature(payload)}`;
}

export function parseGoogleOidcTransaction(
  value: string | undefined,
): GoogleOidcTransaction | null {
  if (!value || value.length > MAX_SERIALIZED_LENGTH) return null;
  const [payload, suppliedSignature, ...extra] = value.split('.');
  if (
    !payload ||
    !suppliedSignature ||
    extra.length > 0 ||
    !/^[A-Za-z0-9_-]+$/.test(payload) ||
    !/^[A-Za-z0-9_-]{43}$/.test(suppliedSignature)
  ) {
    return null;
  }

  try {
    if (!safeEqual(signature(payload), suppliedSignature)) return null;
    const parsed = JSON.parse(
      Buffer.from(payload, 'base64url').toString('utf8'),
    ) as Partial<GoogleOidcTransaction>;
    const intent = onboardingIntent(parsed.intent);
    const returnTo =
      typeof parsed.returnTo === 'string' ? strictRelativeReturnTo(parsed.returnTo) : null;
    const invitationCode = normalizeInvitationCode(parsed.invitationCode);
    const now = Date.now();
    if (
      !intent ||
      returnTo === null ||
      returnTo !== parsed.returnTo ||
      invitationCode === null ||
      (intent !== 'FAMILY' && invitationCode !== undefined) ||
      typeof parsed.createdAt !== 'number' ||
      !Number.isSafeInteger(parsed.createdAt) ||
      parsed.createdAt > now ||
      now - parsed.createdAt > TRANSACTION_TTL_SECONDS * 1000 ||
      typeof parsed.codeVerifier !== 'string' ||
      !CODE_VERIFIER_PATTERN.test(parsed.codeVerifier) ||
      typeof parsed.state !== 'string' ||
      !RANDOM_VALUE_PATTERN.test(parsed.state) ||
      typeof parsed.nonce !== 'string' ||
      !RANDOM_VALUE_PATTERN.test(parsed.nonce)
    ) {
      return null;
    }

    return {
      codeVerifier: parsed.codeVerifier,
      createdAt: parsed.createdAt,
      intent,
      ...(invitationCode ? { invitationCode } : {}),
      nonce: parsed.nonce,
      returnTo,
      state: parsed.state,
    };
  } catch {
    return null;
  }
}

export function googleOidcStateMatches(
  transaction: GoogleOidcTransaction,
  suppliedState: string | null,
): boolean {
  return suppliedState !== null && safeEqual(transaction.state, suppliedState);
}

export function googleOidcTransactionCookieName(): string {
  return process.env.NODE_ENV === 'production' ? PRODUCTION_COOKIE : DEVELOPMENT_COOKIE;
}

export function googleOidcTransactionCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: TRANSACTION_TTL_SECONDS,
  };
}
