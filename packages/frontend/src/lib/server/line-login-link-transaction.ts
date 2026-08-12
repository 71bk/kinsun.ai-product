import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { codeChallenge } from './oauth-transaction';

const DEVELOPMENT_COOKIE = 'kinsun_line_login_link';
const PRODUCTION_COOKIE = '__Host-kinsun_line_login_link';
const TRANSACTION_TTL_SECONDS = 10 * 60;

export interface LineLoginLinkTransaction {
  codeVerifier: string;
  createdAt: number;
  destinationFingerprint: string;
  nonce: string;
  state: string;
}

function randomValue(): string {
  return randomBytes(32).toString('base64url');
}

function signingSecret(): string {
  const secret = process.env.LINE_LOGIN_LINK_TRANSACTION_SECRET;
  if (!secret || Buffer.byteLength(secret, 'utf8') < 32) {
    throw new Error('LINE Login link transaction secret is unavailable');
  }
  if (
    secret === process.env.COGNITO_OAUTH_TRANSACTION_SECRET ||
    secret === process.env.LINE_LOGIN_CHANNEL_SECRET ||
    secret === process.env.LINE_CHANNEL_SECRET
  ) {
    throw new Error('LINE Login link transaction secret must be independent');
  }
  return secret;
}

function signature(payload: string): string {
  return createHmac('sha256', signingSecret()).update(payload).digest('base64url');
}

function destinationFingerprint(cognitoUsername: string): string {
  if (!cognitoUsername || cognitoUsername.length > 256 || /\s/.test(cognitoUsername)) {
    throw new Error('Invalid Cognito linking destination');
  }
  return createHmac('sha256', signingSecret())
    .update('line-login-destination\0', 'utf8')
    .update(cognitoUsername, 'utf8')
    .digest('base64url');
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

export function createLineLoginLinkTransaction(cognitoUsername: string): LineLoginLinkTransaction {
  return {
    codeVerifier: randomValue(),
    createdAt: Date.now(),
    destinationFingerprint: destinationFingerprint(cognitoUsername),
    nonce: randomValue(),
    state: randomValue(),
  };
}

export function lineLoginLinkDestinationMatches(
  transaction: LineLoginLinkTransaction,
  cognitoUsername: string,
): boolean {
  try {
    return safeEqual(transaction.destinationFingerprint, destinationFingerprint(cognitoUsername));
  } catch {
    return false;
  }
}

export function lineLoginCodeChallenge(transaction: { codeVerifier: string }): string {
  return codeChallenge(transaction.codeVerifier);
}

export function serializeLineLoginLinkTransaction(transaction: LineLoginLinkTransaction): string {
  const payload = Buffer.from(JSON.stringify(transaction), 'utf8').toString('base64url');
  return `${payload}.${signature(payload)}`;
}

export function parseLineLoginLinkTransaction(
  value: string | undefined,
): LineLoginLinkTransaction | null {
  if (!value) return null;
  const [payload, providedSignature, ...extra] = value.split('.');
  if (!payload || !providedSignature || extra.length > 0) return null;

  try {
    if (!safeEqual(signature(payload), providedSignature)) return null;
    const parsed = JSON.parse(
      Buffer.from(payload, 'base64url').toString('utf8'),
    ) as Partial<LineLoginLinkTransaction>;
    if (
      typeof parsed.codeVerifier !== 'string' ||
      typeof parsed.createdAt !== 'number' ||
      !Number.isSafeInteger(parsed.createdAt) ||
      typeof parsed.destinationFingerprint !== 'string' ||
      typeof parsed.nonce !== 'string' ||
      typeof parsed.state !== 'string' ||
      parsed.createdAt > Date.now() ||
      Date.now() - parsed.createdAt > TRANSACTION_TTL_SECONDS * 1000 ||
      parsed.codeVerifier.length < 43 ||
      parsed.codeVerifier.length > 128 ||
      parsed.destinationFingerprint.length !== 43 ||
      parsed.nonce.length < 32 ||
      parsed.nonce.length > 128 ||
      parsed.state.length < 32 ||
      parsed.state.length > 128
    ) {
      return null;
    }
    return parsed as LineLoginLinkTransaction;
  } catch {
    return null;
  }
}

export function lineLoginLinkStateMatches(
  transaction: LineLoginLinkTransaction,
  suppliedState: string | null,
): boolean {
  return suppliedState !== null && safeEqual(transaction.state, suppliedState);
}

export function lineLoginLinkCookieName(): string {
  return process.env.NODE_ENV === 'production' ? PRODUCTION_COOKIE : DEVELOPMENT_COOKIE;
}

export function lineLoginLinkCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: TRANSACTION_TTL_SECONDS,
  };
}
