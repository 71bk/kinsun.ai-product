import { NextRequest, NextResponse } from 'next/server';
import { accessTokenCookieName } from '@/lib/server/auth-cookie';
import { CognitoIdentityError, linkLineLoginIdentity } from '@/lib/server/cognito-identities';
import {
  lineLoginLinkCookieName,
  lineLoginLinkCookieOptions,
  lineLoginLinkStateMatches,
  parseLineLoginLinkTransaction,
} from '@/lib/server/line-login-link-transaction';
import {
  exchangeAndVerifyLineLoginCode,
  getLineLoginOAuthConfig,
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
  response.cookies.set(lineLoginLinkCookieName(), '', {
    ...lineLoginLinkCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
  return response;
}

function failureFor(error: unknown): string {
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

export async function GET(request: NextRequest): Promise<Response> {
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
    return redirect('/account/sign-in-methods?error=line_link_failed');
  }

  let config: LineLoginOAuthConfig | null = null;
  let temporaryAccessToken: string | null = null;
  let stage: 'token_exchange' | 'cognito_link' = 'token_exchange';
  try {
    config = getLineLoginOAuthConfig();
    const result = await exchangeAndVerifyLineLoginCode(config, codes[0] ?? '', transaction);
    temporaryAccessToken = result.tokenSet.accessToken;
    stage = 'cognito_link';
    const linkResult = await linkLineLoginIdentity(
      request.cookies.get(accessTokenCookieName())?.value,
      result.identity,
      transaction,
    );
    return redirect(
      `/account/sign-in-methods?status=${
        linkResult === 'ALREADY_LINKED' ? 'already_linked' : 'linked'
      }`,
    );
  } catch (error) {
    console.error('[auth] LINE Login linking callback failed', { stage });
    return redirect(`/account/sign-in-methods?error=${failureFor(error)}`);
  } finally {
    if (config && temporaryAccessToken) {
      await revokeLineLoginToken(config, temporaryAccessToken);
    }
  }
}
