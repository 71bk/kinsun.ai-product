import { timingSafeEqual } from 'node:crypto';
import { logAuthDiagnostic } from './auth-diagnostics';
import { codeChallenge } from './oauth-transaction';
import type { GoogleOidcTransaction } from './google-oidc-transaction';

const AUTHORIZATION_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth';
const TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token';
const CALLBACK_PATH = '/backend/auth/google/callback';
const REQUIRED_SCOPES = ['openid', 'email', 'profile'];
const TOKEN_EXCHANGE_TIMEOUT_MS = 10_000;
const MAX_AUTHORIZATION_CODE_LENGTH = 4096;
const MAX_ID_TOKEN_LENGTH = 16_384;
const MAX_TOKEN_RESPONSE_BYTES = 64 * 1024;
const ID_TOKEN_PATTERN = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
const LOGGABLE_REQUEST_ERROR_TYPES = new Set(['AbortError', 'TimeoutError', 'TypeError']);

export interface GoogleOidcBffConfig {
  callbackUrl: URL;
  clientId: string;
  clientSecret: string;
}

export interface GoogleOidcExchangeResult {
  idToken: string;
}

function normalizedCredential(
  value: string | undefined,
  name: string,
  minimumLength: number,
): string {
  if (
    !value ||
    value !== value.trim() ||
    value.length < minimumLength ||
    value.length > 512 ||
    /\s/.test(value)
  ) {
    throw new Error(`${name} is unavailable`);
  }
  return value;
}

function frontendOrigin(): URL {
  const rawValue = process.env.FRONTEND_ORIGIN;
  if (!rawValue) throw new Error('FRONTEND_ORIGIN is unavailable');
  const value = new URL(rawValue);
  if (
    value.username ||
    value.password ||
    value.pathname !== '/' ||
    value.search ||
    value.hash ||
    (value.protocol !== 'https:' && value.protocol !== 'http:')
  ) {
    throw new Error('FRONTEND_ORIGIN is invalid');
  }
  if (process.env.NODE_ENV === 'production' && value.protocol !== 'https:') {
    throw new Error('FRONTEND_ORIGIN must use HTTPS in production');
  }
  return value;
}

export function getGoogleOidcBffConfig(): GoogleOidcBffConfig {
  const clientId = normalizedCredential(process.env.GOOGLE_OIDC_CLIENT_ID, 'Google client ID', 8);
  const clientSecret = normalizedCredential(
    process.env.GOOGLE_OIDC_CLIENT_SECRET,
    'Google client secret',
    8,
  );
  if (clientSecret === process.env.GOOGLE_OIDC_TRANSACTION_SECRET) {
    throw new Error('Google client and transaction secrets must be independent');
  }
  return {
    callbackUrl: new URL(CALLBACK_PATH, frontendOrigin()),
    clientId,
    clientSecret,
  };
}

export function buildGoogleOidcAuthorizationUrl(
  config: GoogleOidcBffConfig,
  transaction: GoogleOidcTransaction,
): URL {
  const target = new URL(AUTHORIZATION_ENDPOINT);
  target.searchParams.set('client_id', config.clientId);
  target.searchParams.set('code_challenge', codeChallenge(transaction.codeVerifier));
  target.searchParams.set('code_challenge_method', 'S256');
  target.searchParams.set('nonce', transaction.nonce);
  target.searchParams.set('prompt', 'select_account');
  target.searchParams.set('redirect_uri', config.callbackUrl.toString());
  target.searchParams.set('response_type', 'code');
  target.searchParams.set('scope', REQUIRED_SCOPES.join(' '));
  target.searchParams.set('state', transaction.state);
  return target;
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left, 'ascii');
  const rightBuffer = Buffer.from(right, 'ascii');
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function idTokenNonce(idToken: string): string | null {
  const parts = idToken.split('.');
  if (parts.length !== 3 || !parts[1]) return null;
  try {
    const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8')) as {
      nonce?: unknown;
    };
    return typeof payload.nonce === 'string' ? payload.nonce : null;
  } catch {
    return null;
  }
}

function normalizedIdToken(value: unknown): string | null {
  if (
    typeof value !== 'string' ||
    !value ||
    value.length > MAX_ID_TOKEN_LENGTH ||
    !ID_TOKEN_PATTERN.test(value)
  ) {
    return null;
  }
  return value;
}

function safeRequestErrorType(error: unknown): string {
  const value = error instanceof Error ? error.name : '';
  return LOGGABLE_REQUEST_ERROR_TYPES.has(value) ? value : 'UnknownError';
}

/**
 * Exchange a direct Google authorization code without retaining access or
 * refresh tokens. The ID token is correlated to the BFF nonce here, but remains
 * untrusted until Core independently verifies its signature and claims.
 */
export async function exchangeGoogleOidcAuthorizationCode(
  config: GoogleOidcBffConfig,
  code: string,
  transaction: GoogleOidcTransaction,
): Promise<GoogleOidcExchangeResult> {
  if (
    !code ||
    code.length > MAX_AUTHORIZATION_CODE_LENGTH ||
    /\s/.test(code) ||
    !/^[\x21-\x7e]+$/.test(code)
  ) {
    throw new Error('Invalid Google authorization code');
  }

  const body = new URLSearchParams({
    client_id: config.clientId,
    client_secret: config.clientSecret,
    code,
    code_verifier: transaction.codeVerifier,
    grant_type: 'authorization_code',
    redirect_uri: config.callbackUrl.toString(),
  });
  let response: Response;
  try {
    response = await fetch(TOKEN_ENDPOINT, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(TOKEN_EXCHANGE_TIMEOUT_MS),
    });
  } catch (error) {
    logAuthDiagnostic('Google token exchange request failed', {
      error_type: safeRequestErrorType(error),
    });
    throw new Error('Google token exchange failed');
  }
  if (!response.ok) {
    logAuthDiagnostic('Google token exchange rejected', { status: response.status });
    throw new Error('Google token exchange failed');
  }

  const responseBody = await response.text();
  if (Buffer.byteLength(responseBody, 'utf8') > MAX_TOKEN_RESPONSE_BYTES) {
    throw new Error('Invalid Google token response');
  }
  let payload: { id_token?: unknown } | null = null;
  try {
    const parsed = JSON.parse(responseBody) as unknown;
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      payload = parsed as { id_token?: unknown };
    }
  } catch {
    payload = null;
  }

  const idToken = normalizedIdToken(payload?.id_token);
  const nonce = idToken === null ? null : idTokenNonce(idToken);
  if (!idToken || !nonce || !safeEqual(nonce, transaction.nonce)) {
    logAuthDiagnostic('Google token response validation failed', {
      id_token_valid: Boolean(idToken),
      nonce_present: nonce !== null,
      nonce_matches: nonce !== null && safeEqual(nonce, transaction.nonce),
    });
    throw new Error('Invalid Google token response');
  }
  return { idToken };
}
