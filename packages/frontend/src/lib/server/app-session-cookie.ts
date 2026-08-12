const DEVELOPMENT_APP_SESSION_COOKIE = 'kinsun_session';
const PRODUCTION_APP_SESSION_COOKIE = '__Host-kinsun_session';
const APP_SESSION_PATTERN = /^ks1_[A-Za-z0-9_-]{43}$/;

export function appSessionCookieName(): string {
  return process.env.NODE_ENV === 'production'
    ? PRODUCTION_APP_SESSION_COOKIE
    : DEVELOPMENT_APP_SESSION_COOKIE;
}

export function normalizeAppSession(value: unknown): string | null {
  return typeof value === 'string' && APP_SESSION_PATTERN.test(value) ? value : null;
}

export function appSessionCookieOptions(maxAgeSeconds?: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    ...(maxAgeSeconds === undefined ? {} : { maxAge: maxAgeSeconds }),
  };
}

export function appSessionMaxAge(idleExpiresAt: string, absoluteExpiresAt: string): number {
  const expiresAt = Math.min(Date.parse(idleExpiresAt), Date.parse(absoluteExpiresAt));
  const seconds = Math.floor((expiresAt - Date.now()) / 1000);
  if (!Number.isFinite(seconds) || seconds < 1) {
    throw new Error('App Session expiry is invalid');
  }
  return seconds;
}

export function normalizeBrowserAuthCredential(
  rawAppSession: unknown,
  rawAccessToken: unknown,
): string | null {
  // Cookie presence selects the validator. A malformed App Session must never
  // fall back to a simultaneously present legacy Cognito credential.
  return rawAppSession === undefined
    ? normalizeAccessToken(rawAccessToken)
    : normalizeAppSession(rawAppSession);
}

export function browserAuthCookieNames(): readonly string[] {
  return [appSessionCookieName(), accessTokenCookieName()];
}
import { accessTokenCookieName, normalizeAccessToken } from './auth-cookie';
