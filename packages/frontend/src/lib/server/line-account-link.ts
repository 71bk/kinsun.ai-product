import { normalizeAppSession } from './app-session-cookie';
import { resolveCoreApiBaseUrl } from './core-api-url';

const DEVELOPMENT_LINE_LINK_COOKIE = 'kinsun_line_link';
const PRODUCTION_LINE_LINK_COOKIE = '__Host-kinsun_line_link';
const LINE_LINK_TTL_SECONDS = 10 * 60;
const MAX_LINK_TOKEN_LENGTH = 2048;
const CORE_TIMEOUT_MS = 30_000;

export interface CoreLineLinkChallengeResult {
  accountLinkUrl?: string;
  status: number;
}

export function lineLinkCookieName(): string {
  return process.env.NODE_ENV === 'production'
    ? PRODUCTION_LINE_LINK_COOKIE
    : DEVELOPMENT_LINE_LINK_COOKIE;
}

export function lineLinkCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: LINE_LINK_TTL_SECONDS,
  };
}

export function normalizeLineLinkToken(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  if (
    !value ||
    value !== value.trim() ||
    value.length > MAX_LINK_TOKEN_LENGTH ||
    /\s/.test(value)
  ) {
    return null;
  }
  return value;
}

function officialAccountLinkUrl(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 4096) return null;
  try {
    const url = new URL(value);
    if (
      url.origin !== 'https://access.line.me' ||
      url.pathname !== '/dialog/bot/accountLink' ||
      url.username ||
      url.password ||
      url.hash
    ) {
      return null;
    }
    for (const key of url.searchParams.keys()) {
      if (key !== 'linkToken' && key !== 'nonce') return null;
    }
    const linkTokens = url.searchParams.getAll('linkToken');
    const nonces = url.searchParams.getAll('nonce');
    if (
      linkTokens.length !== 1 ||
      nonces.length !== 1 ||
      normalizeLineLinkToken(linkTokens[0]) === null ||
      !nonces[0] ||
      nonces[0] !== nonces[0].trim() ||
      nonces[0].length < 10 ||
      nonces[0].length > 255 ||
      /\s/.test(nonces[0])
    ) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

export async function createCoreLineLinkChallenge(
  rawAppSession: unknown,
  rawLinkToken: unknown,
): Promise<CoreLineLinkChallengeResult> {
  const appSession = normalizeAppSession(rawAppSession);
  const linkToken = normalizeLineLinkToken(rawLinkToken);
  const baseUrl = resolveCoreApiBaseUrl({ allowLocalDefault: true });
  if (!appSession || !linkToken || !baseUrl) return { status: 503 };

  try {
    const response = await fetch(new URL('api/v1/me/line-link-challenges', baseUrl), {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${appSession}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ link_token: linkToken }),
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.timeout(CORE_TIMEOUT_MS),
    });
    if (!response.ok) return { status: response.status };
    const body = (await response.json().catch(() => null)) as {
      data?: { account_link_url?: unknown };
    } | null;
    const accountLinkUrl = officialAccountLinkUrl(body?.data?.account_link_url);
    return accountLinkUrl ? { status: response.status, accountLinkUrl } : { status: 502 };
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === 'TimeoutError';
    return { status: timedOut ? 504 : 502 };
  }
}
