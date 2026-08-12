import { NextRequest, NextResponse } from 'next/server';
import {
  appSessionCookieName,
  appSessionCookieOptions,
  appSessionMaxAge,
} from '@/lib/server/app-session-cookie';
import { accessTokenCookieName, accessTokenCookieOptions } from '@/lib/server/auth-cookie';
import { logAuthDiagnostic } from '@/lib/server/auth-diagnostics';
import {
  exchangeLineOidcAuthorizationCode,
  getLineLoginOAuthConfig,
  lineDirectOidcEnabled,
  revokeLineLoginToken,
  type LineLoginOAuthConfig,
} from '@/lib/server/line-login-oauth';
import { LineOidcCallbackError, validateLineOidcCallback } from '@/lib/server/line-oidc-callback';
import { handoffLineOidcToCore } from '@/lib/server/line-oidc-core-handoff';
import {
  lineOidcTransactionCookieName,
  lineOidcTransactionCookieOptions,
} from '@/lib/server/line-oidc-transaction';
import {
  createLinePendingOnboarding,
  linePendingOnboardingCookieName,
  linePendingOnboardingCookieOptions,
  serializeLinePendingOnboarding,
} from '@/lib/server/line-pending-onboarding';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

function redirect(location: string): NextResponse {
  return noStore(new NextResponse(null, { status: 303, headers: { Location: location } }));
}

function clearLineTransaction(response: NextResponse): void {
  response.cookies.set(lineOidcTransactionCookieName(), '', {
    ...lineOidcTransactionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
}

function clearCognitoCredential(response: NextResponse): void {
  response.cookies.set(accessTokenCookieName(), '', {
    ...accessTokenCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
}

function failedCallback(clearCurrentTransaction = true): Response {
  const response = redirect('/sign-in?error=oauth_failed');
  if (clearCurrentTransaction) clearLineTransaction(response);
  return response;
}

export async function GET(request: NextRequest): Promise<Response> {
  if (!lineDirectOidcEnabled()) return new Response(null, { status: 404 });

  let clearCurrentTransaction = true;
  let stage: 'callback' | 'core_handoff' | 'token_exchange' = 'callback';
  let config: LineLoginOAuthConfig | null = null;
  let temporaryAccessToken: string | null = null;
  try {
    const validated = validateLineOidcCallback(
      request.nextUrl.searchParams,
      request.cookies.get(lineOidcTransactionCookieName())?.value,
    );
    stage = 'token_exchange';
    config = getLineLoginOAuthConfig('login');
    const exchange = await exchangeLineOidcAuthorizationCode(
      config,
      validated.authorizationCode,
      validated.transaction,
    );
    temporaryAccessToken = exchange.tokenSet.accessToken;
    stage = 'core_handoff';
    const handoff = await handoffLineOidcToCore(exchange.tokenSet.idToken, validated.transaction);
    if (handoff.status === 'AUTHENTICATED') {
      const response = redirect(validated.transaction.returnTo);
      clearLineTransaction(response);
      clearCognitoCredential(response);
      response.cookies.set(
        appSessionCookieName(),
        handoff.sessionToken,
        appSessionCookieOptions(appSessionMaxAge(handoff.idleExpiresAt, handoff.absoluteExpiresAt)),
      );
      response.cookies.set(linePendingOnboardingCookieName(), '', {
        ...linePendingOnboardingCookieOptions(),
        expires: new Date(0),
        maxAge: 0,
      });
      return response;
    }

    const pending = createLinePendingOnboarding(handoff, validated.transaction);
    const response = redirect('/auth/line/complete');
    clearLineTransaction(response);
    response.cookies.set(
      linePendingOnboardingCookieName(),
      serializeLinePendingOnboarding(pending),
      linePendingOnboardingCookieOptions(
        Math.max(1, Math.floor((pending.expiresAt - Date.now()) / 1000)),
      ),
    );
    return response;
  } catch (error) {
    if (error instanceof LineOidcCallbackError) {
      clearCurrentTransaction = error.clearCurrentTransaction;
      logAuthDiagnostic('Direct LINE callback rejected', { reason: error.reason });
    } else {
      logAuthDiagnostic('Direct LINE callback failed', { stage });
    }
    return failedCallback(clearCurrentTransaction);
  } finally {
    if (config && temporaryAccessToken) {
      await revokeLineLoginToken(config, temporaryAccessToken);
    }
  }
}
