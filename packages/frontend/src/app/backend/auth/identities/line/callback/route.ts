import { NextRequest, NextResponse } from 'next/server';
import { appSessionCookieName, normalizeAppSession } from '@/lib/server/app-session-cookie';
import { accessTokenCookieName } from '@/lib/server/auth-cookie';
import { CognitoIdentityError, linkLineLoginIdentity } from '@/lib/server/cognito-identities';
import {
  createPendingLineAccountMerge,
  lineAccountMergeCookieName,
  lineAccountMergeCookieOptions,
  serializePendingLineAccountMerge,
} from '@/lib/server/line-account-merge';
import { linkLineIdentityWithCore } from '@/lib/server/line-account-link-core';
import {
  lineAccountLinkCookieName,
  lineAccountLinkCookieOptions,
  lineAccountLinkOwnsSession,
  lineAccountLinkStateMatches,
  parseLineAccountLinkTransaction,
} from '@/lib/server/line-account-link-transaction';
import {
  lineLoginLinkCookieName,
  lineLoginLinkCookieOptions,
  lineLoginLinkStateMatches,
  parseLineLoginLinkTransaction,
} from '@/lib/server/line-login-link-transaction';
import {
  exchangeAndVerifyLineLoginCode,
  exchangeLineOidcAuthorizationCode,
  getLineLoginOAuthConfig,
  lineDirectOidcEnabled,
  lineLoginEnabled,
  revokeLineLoginToken,
  type LineLoginOAuthConfig,
} from '@/lib/server/line-login-oauth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function redirect(location: string): NextResponse {
  const response = new NextResponse(null, {
    status: 303,
    headers: {
      'Cache-Control': 'no-store',
      Location: location,
      'X-Content-Type-Options': 'nosniff',
    },
  });
  response.cookies.set(lineAccountLinkCookieName(), '', {
    ...lineAccountLinkCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return response;
}

function legacyRedirect(location: string): NextResponse {
  const response = new NextResponse(null, {
    status: 303,
    headers: {
      'Cache-Control': 'no-store',
      Location: location,
      'X-Content-Type-Options': 'nosniff',
    },
  });
  response.cookies.set(lineLoginLinkCookieName(), '', {
    ...lineLoginLinkCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return response;
}

function legacyFailure(error: unknown): string {
  if (!(error instanceof CognitoIdentityError)) return 'line_link_failed';
  switch (error.reason) {
    case 'AUTHENTICATION_REQUIRED':
      return 'session_expired';
    case 'GOOGLE_REQUIRED':
      return 'google_required';
    case 'IDENTITY_CONFLICT':
      return 'line_identity_conflict';
    case 'LINE_EMAIL_MISMATCH':
      return 'line_email_mismatch';
    case 'LINK_DESTINATION_CHANGED':
      return 'link_destination_changed';
    default:
      return 'line_link_failed';
  }
}

async function legacyCallback(request: NextRequest): Promise<Response> {
  const codes = request.nextUrl.searchParams.getAll('code');
  const states = request.nextUrl.searchParams.getAll('state');
  const transaction = parseLineLoginLinkTransaction(
    request.cookies.get(lineLoginLinkCookieName())?.value,
  );
  if (
    codes.length !== 1 ||
    states.length !== 1 ||
    request.nextUrl.searchParams.has('error') ||
    !transaction ||
    !lineLoginLinkStateMatches(transaction, states[0] ?? null)
  ) {
    return legacyRedirect('/account/sign-in-methods?error=line_link_failed');
  }
  let config: LineLoginOAuthConfig | null = null;
  let temporaryAccessToken: string | null = null;
  let stage: 'token_exchange' | 'cognito_link' = 'token_exchange';
  try {
    config = getLineLoginOAuthConfig();
    const result = await exchangeAndVerifyLineLoginCode(config, codes[0] ?? '', transaction);
    temporaryAccessToken = result.tokenSet.accessToken;
    stage = 'cognito_link';
    const linked = await linkLineLoginIdentity(
      request.cookies.get(accessTokenCookieName())?.value,
      result.identity,
      transaction,
    );
    return legacyRedirect(
      `/account/sign-in-methods?status=${linked === 'ALREADY_LINKED' ? 'already_linked' : 'linked'}`,
    );
  } catch (error) {
    console.error('[auth] LINE Login linking callback failed', { stage });
    return legacyRedirect(`/account/sign-in-methods?error=${legacyFailure(error)}`);
  } finally {
    if (config && temporaryAccessToken) await revokeLineLoginToken(config, temporaryAccessToken);
  }
}

export async function GET(request: NextRequest): Promise<Response> {
  const directTransaction = parseLineAccountLinkTransaction(
    request.cookies.get(lineAccountLinkCookieName())?.value,
  );
  if (!directTransaction && lineLoginEnabled()) return legacyCallback(request);
  if (!lineDirectOidcEnabled()) return new Response(null, { status: 404 });
  const codes = request.nextUrl.searchParams.getAll('code');
  const states = request.nextUrl.searchParams.getAll('state');
  const appSession = normalizeAppSession(request.cookies.get(appSessionCookieName())?.value);
  const transaction = directTransaction;
  if (
    codes.length !== 1 ||
    states.length !== 1 ||
    request.nextUrl.searchParams.has('error') ||
    !appSession ||
    !transaction ||
    !lineAccountLinkStateMatches(transaction, states[0] ?? null) ||
    !lineAccountLinkOwnsSession(transaction, appSession)
  ) {
    return redirect('/account/sign-in-methods?error=line_link_failed');
  }

  let config: LineLoginOAuthConfig | null = null;
  let temporaryAccessToken: string | null = null;
  try {
    config = getLineLoginOAuthConfig('direct-link');
    const exchange = await exchangeLineOidcAuthorizationCode(config, codes[0] ?? '', transaction);
    temporaryAccessToken = exchange.tokenSet.accessToken;
    const result = await linkLineIdentityWithCore(
      appSession,
      exchange.tokenSet.idToken,
      transaction.nonce,
    );
    if (result.status === 'LINKED' || result.status === 'ALREADY_LINKED') {
      return redirect(
        `/account/sign-in-methods?status=${
          result.status === 'LINKED' ? 'linked' : 'already_linked'
        }`,
      );
    }
    if (result.status === 'MANUAL_REVIEW_REQUIRED') {
      return redirect('/account/sign-in-methods?error=manual_review_required');
    }
    if (result.status !== 'MERGE_REQUIRED') {
      return redirect('/account/sign-in-methods?error=line_link_failed');
    }
    const pending = createPendingLineAccountMerge(result.mergeToken, result.expiresAt);
    const response = redirect('/account/sign-in-methods?status=merge_required');
    response.cookies.set(
      lineAccountMergeCookieName(),
      serializePendingLineAccountMerge(pending),
      lineAccountMergeCookieOptions(
        Math.max(1, Math.floor((pending.expiresAt - Date.now()) / 1000)),
      ),
    );
    return response;
  } catch {
    return redirect('/account/sign-in-methods?error=line_link_failed');
  } finally {
    if (config && temporaryAccessToken) {
      await revokeLineLoginToken(config, temporaryAccessToken);
    }
  }
}
