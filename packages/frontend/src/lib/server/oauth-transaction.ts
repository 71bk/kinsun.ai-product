import { createHash } from 'node:crypto';
const ALLOWED_RETURN_PATHS = new Set([
  '/',
  '/account/sign-in-methods',
  '/consent',
  '/dashboard',
  '/family',
  '/line/account-link',
  '/onboarding/resolve',
  '/sign-in',
]);

export type LoginProvider = 'GOOGLE' | 'LINE';
export type OnboardingIntent = 'ELDER' | 'FAMILY' | 'STAFF';

export function strictRelativeReturnTo(value: string | null): string | null {
  if (value === null || value === '') return '/onboarding/resolve';
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return null;

  try {
    const parsed = new URL(value, 'https://frontend.invalid');
    if (parsed.origin !== 'https://frontend.invalid') return null;
    if (!ALLOWED_RETURN_PATHS.has(parsed.pathname) || parsed.search || parsed.hash) return null;
    return parsed.pathname;
  } catch {
    return null;
  }
}

export function onboardingIntent(value: unknown): OnboardingIntent | null {
  return value === 'ELDER' || value === 'FAMILY' || value === 'STAFF' ? value : null;
}

export function loginProvider(value: unknown): LoginProvider | null {
  return value === undefined || value === null || value === ''
    ? 'GOOGLE'
    : value === 'GOOGLE' || value === 'LINE'
      ? value
      : null;
}

export function normalizeInvitationCode(value: unknown): string | undefined | null {
  if (value === undefined || value === null || value === '') return undefined;
  if (typeof value !== 'string') return null;
  const code = value.trim();
  if (code.length < 16 || code.length > 24 || /[\r\n\0]/.test(code)) return null;
  return code;
}

export function codeChallenge(codeVerifier: string): string {
  return createHash('sha256').update(codeVerifier).digest('base64url');
}
