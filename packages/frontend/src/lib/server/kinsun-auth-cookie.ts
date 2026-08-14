import { appSessionCookieOptions } from './app-session-cookie';
import type { NextResponse } from 'next/server';

const CHALLENGE_COOKIE = 'kinsun_email_challenge';
const INVITATION_COOKIE = 'kinsun_email_invitation';
const RETURN_TO_COOKIE = 'kinsun_email_return_to';
const CHALLENGE_PATTERN = /^ke1_[A-Za-z0-9_-]{43}$/;

export function kinsunChallengeCookieName(): string {
  return CHALLENGE_COOKIE;
}

export function kinsunInvitationCookieName(): string {
  return INVITATION_COOKIE;
}

export function kinsunReturnToCookieName(): string {
  return RETURN_TO_COOKIE;
}

export function kinsunAuthCookieOptions(maxAge: number) {
  return appSessionCookieOptions(maxAge);
}

export function normalizeKinsunChallenge(value: unknown): string | null {
  return typeof value === 'string' && CHALLENGE_PATTERN.test(value) ? value : null;
}

export function clearKinsunAuthCookies(response: NextResponse): void {
  const expired = { ...appSessionCookieOptions(0), expires: new Date(0), maxAge: 0 };
  response.cookies.set(CHALLENGE_COOKIE, '', expired);
  response.cookies.set(INVITATION_COOKIE, '', expired);
  response.cookies.set(RETURN_TO_COOKIE, '', expired);
}
