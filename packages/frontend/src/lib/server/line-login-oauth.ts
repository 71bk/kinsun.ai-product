import type { LineLoginLinkTransaction } from './line-login-link-transaction';
import { lineLoginCodeChallenge } from './line-login-link-transaction';

const LINE_AUTHORIZATION_ENDPOINT = 'https://access.line.me/oauth2/v2.1/authorize';
const LINE_TOKEN_ENDPOINT = 'https://api.line.me/oauth2/v2.1/token';
const LINE_VERIFY_ID_TOKEN_ENDPOINT = 'https://api.line.me/oauth2/v2.1/verify';
const LINE_REVOKE_ENDPOINT = 'https://api.line.me/oauth2/v2.1/revoke';
const LINE_ISSUER = 'https://access.line.me';
const HTTP_TIMEOUT_MS = 10_000;
const MAX_TOKEN_LENGTH = 8_192;

export interface LineLoginOAuthConfig {
  callbackUrl: URL;
  channelId: string;
  channelSecret: string;
}

export interface VerifiedLineLoginIdentity {
  email: string;
  subject: string;
}

interface LineLoginTokenSet {
  accessToken: string;
}

function safeAbsoluteUrl(rawValue: string | undefined, name: string): URL {
  if (!rawValue) throw new Error(`${name} is unavailable`);
  const value = new URL(rawValue);
  if (
    value.username ||
    value.password ||
    (value.protocol !== 'https:' && value.protocol !== 'http:')
  ) {
    throw new Error(`${name} is invalid`);
  }
  if (process.env.NODE_ENV === 'production' && value.protocol !== 'https:') {
    throw new Error(`${name} must use HTTPS in production`);
  }
  return value;
}

function channelId(): string {
  const value = process.env.LINE_LOGIN_CHANNEL_ID;
  if (!value || !/^\d{5,32}$/.test(value)) {
    throw new Error('LINE_LOGIN_CHANNEL_ID is unavailable');
  }
  return value;
}

function channelSecret(): string {
  const value = process.env.LINE_LOGIN_CHANNEL_SECRET;
  if (!value || value.length < 16 || value.length > 256 || /\s/.test(value)) {
    throw new Error('LINE_LOGIN_CHANNEL_SECRET is unavailable');
  }
  if (
    value === process.env.LINE_CHANNEL_SECRET ||
    value === process.env.LINE_IDENTITY_HMAC_SECRET ||
    value === process.env.LINE_LOGIN_LINK_TRANSACTION_SECRET
  ) {
    throw new Error('LINE Login channel secret must be independent');
  }
  return value;
}

export function lineLoginEnabled(): boolean {
  return process.env.LINE_LOGIN_ENABLED?.trim().toLowerCase() === 'true';
}

export function getLineLoginOAuthConfig(): LineLoginOAuthConfig {
  if (!lineLoginEnabled()) throw new Error('LINE Login is disabled');
  const callbackUrl = safeAbsoluteUrl(
    process.env.LINE_LOGIN_LINK_CALLBACK_URL,
    'LINE_LOGIN_LINK_CALLBACK_URL',
  );
  const frontendOrigin = safeAbsoluteUrl(process.env.FRONTEND_ORIGIN, 'FRONTEND_ORIGIN');
  if (
    callbackUrl.origin !== frontendOrigin.origin ||
    callbackUrl.pathname !== '/backend/auth/identities/line/callback' ||
    callbackUrl.search ||
    callbackUrl.hash
  ) {
    throw new Error('LINE Login callback must use the fixed frontend callback path');
  }
  return { callbackUrl, channelId: channelId(), channelSecret: channelSecret() };
}

export function buildLineLoginLinkAuthorizationUrl(
  config: LineLoginOAuthConfig,
  transaction: LineLoginLinkTransaction,
): URL {
  const target = new URL(LINE_AUTHORIZATION_ENDPOINT);
  target.searchParams.set('response_type', 'code');
  target.searchParams.set('client_id', config.channelId);
  target.searchParams.set('redirect_uri', config.callbackUrl.toString());
  target.searchParams.set('state', transaction.state);
  target.searchParams.set('scope', 'openid profile email');
  target.searchParams.set('nonce', transaction.nonce);
  target.searchParams.set('code_challenge', lineLoginCodeChallenge(transaction));
  target.searchParams.set('code_challenge_method', 'S256');
  target.searchParams.set('max_age', '300');
  return target;
}

function normalizedEmail(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const email = value.trim().toLowerCase();
  if (!email || email.length > 320 || /[\s\r\n\0]/.test(email) || !email.includes('@')) {
    return null;
  }
  return email;
}

export async function exchangeAndVerifyLineLoginCode(
  config: LineLoginOAuthConfig,
  code: string,
  transaction: LineLoginLinkTransaction,
): Promise<{ identity: VerifiedLineLoginIdentity; tokenSet: LineLoginTokenSet }> {
  if (!code || code.length > 4_096 || /\s/.test(code)) {
    throw new Error('Invalid LINE authorization code');
  }
  const tokenResponse = await fetch(LINE_TOKEN_ENDPOINT, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: config.callbackUrl.toString(),
      client_id: config.channelId,
      client_secret: config.channelSecret,
      code_verifier: transaction.codeVerifier,
    }),
    cache: 'no-store',
    redirect: 'error',
    signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
  });
  if (!tokenResponse.ok) throw new Error('LINE token exchange failed');
  const tokenBody = (await tokenResponse.json().catch(() => null)) as {
    access_token?: unknown;
    id_token?: unknown;
  } | null;
  if (
    !tokenBody ||
    typeof tokenBody.access_token !== 'string' ||
    !tokenBody.access_token ||
    tokenBody.access_token.length > MAX_TOKEN_LENGTH
  ) {
    throw new Error('Invalid LINE token response');
  }
  const temporaryAccessToken = tokenBody.access_token;

  try {
    if (
      typeof tokenBody.id_token !== 'string' ||
      !tokenBody.id_token ||
      tokenBody.id_token.length > MAX_TOKEN_LENGTH
    ) {
      throw new Error('Invalid LINE token response');
    }
    const verifyResponse = await fetch(LINE_VERIFY_ID_TOKEN_ENDPOINT, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        id_token: tokenBody.id_token,
        client_id: config.channelId,
        nonce: transaction.nonce,
      }),
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
    });
    if (!verifyResponse.ok) throw new Error('LINE ID token verification failed');
    const verified = (await verifyResponse.json().catch(() => null)) as {
      aud?: unknown;
      email?: unknown;
      exp?: unknown;
      iss?: unknown;
      nonce?: unknown;
      sub?: unknown;
    } | null;
    const email = normalizedEmail(verified?.email);
    if (
      !verified ||
      verified.iss !== LINE_ISSUER ||
      verified.aud !== config.channelId ||
      verified.nonce !== transaction.nonce ||
      typeof verified.exp !== 'number' ||
      !Number.isSafeInteger(verified.exp) ||
      verified.exp * 1000 <= Date.now() ||
      typeof verified.sub !== 'string' ||
      !verified.sub ||
      verified.sub.length > 255 ||
      /\s/.test(verified.sub) ||
      !email
    ) {
      throw new Error('Invalid verified LINE identity');
    }
    return {
      identity: { email, subject: verified.sub },
      tokenSet: { accessToken: temporaryAccessToken },
    };
  } catch (error) {
    await revokeLineLoginToken(config, temporaryAccessToken);
    throw error;
  }
}

export async function revokeLineLoginToken(
  config: LineLoginOAuthConfig,
  accessToken: string,
): Promise<void> {
  if (!accessToken || accessToken.length > MAX_TOKEN_LENGTH) return;
  try {
    await fetch(LINE_REVOKE_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        access_token: accessToken,
        client_id: config.channelId,
        client_secret: config.channelSecret,
      }),
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
    });
  } catch {
    // Token revocation is best-effort; never log the token or response body.
  }
}
