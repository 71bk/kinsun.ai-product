import { NextRequest, NextResponse } from 'next/server';
import { appSessionCookieName, normalizeAppSession } from '@/lib/server/app-session-cookie';
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
  exchangeLineOidcAuthorizationCode,
  getLineLoginOAuthConfig,
  lineDirectOidcEnabled,
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

export async function GET(request: NextRequest): Promise<Response> {
  const directTransaction = parseLineAccountLinkTransaction(
    request.cookies.get(lineAccountLinkCookieName())?.value,
  );
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
