const DEVELOPMENT_ELDER_SESSION_COOKIE = 'kinsun_elder_session';
const PRODUCTION_ELDER_SESSION_COOKIE = '__Host-kinsun_elder_session';
const ELDER_SESSION_PATTERN = /^es1_[A-Za-z0-9_-]{43}$/;

export function elderSessionCookieName(): string {
  return process.env.NODE_ENV === 'production'
    ? PRODUCTION_ELDER_SESSION_COOKIE
    : DEVELOPMENT_ELDER_SESSION_COOKIE;
}

export function normalizeElderSession(value: unknown): string | null {
  return typeof value === 'string' && ELDER_SESSION_PATTERN.test(value) ? value : null;
}

export function elderSessionCookieOptions(maxAgeSeconds?: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict' as const,
    path: '/',
    ...(maxAgeSeconds === undefined ? {} : { maxAge: maxAgeSeconds }),
  };
}

export function elderSessionCookieMaxAge(
  idleExpiresAt: string,
  absoluteExpiresAt: string,
): number {
  const expiresAt = Math.min(Date.parse(idleExpiresAt), Date.parse(absoluteExpiresAt));
  const seconds = Math.floor((expiresAt - Date.now()) / 1000);
  if (!Number.isFinite(seconds) || seconds < 1) {
    throw new Error('Elder Session expiry is invalid');
  }
  return seconds;
}
