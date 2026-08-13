import { NextRequest, NextResponse } from 'next/server';
import {
  appSessionCookieName,
  appSessionCookieOptions,
  appSessionMaxAge,
} from '@/lib/server/app-session-cookie';
import { logAuthDiagnostic } from '@/lib/server/auth-diagnostics';
import {
  createGooglePendingOnboarding,
  googlePendingOnboardingCookieName,
  googlePendingOnboardingCookieOptions,
  serializeGooglePendingOnboarding,
} from '@/lib/server/google-pending-onboarding';
import {
  exchangeGoogleOidcAuthorizationCode,
  getGoogleOidcBffConfig,
  googleDirectOidcEnabled,
} from '@/lib/server/google-oidc';
import {
  GoogleOidcCallbackError,
  validateGoogleOidcCallback,
} from '@/lib/server/google-oidc-callback';
import { handoffGoogleOidcToCore } from '@/lib/server/google-oidc-core-handoff';
import {
  googleOidcTransactionCookieName,
  googleOidcTransactionCookieOptions,
} from '@/lib/server/google-oidc-transaction';

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

function clearGoogleTransaction(response: NextResponse): void {
  response.cookies.set(googleOidcTransactionCookieName(), '', {
    ...googleOidcTransactionCookieOptions(),
    expires: new Date(0),
    maxAge: 0,
  });
}

function failedCallback(clearCurrentTransaction = true): Response {
  const response = redirect('/sign-in?error=oauth_failed');
  if (clearCurrentTransaction) clearGoogleTransaction(response);
  return response;
}

export async function GET(request: NextRequest): Promise<Response> {
  if (!googleDirectOidcEnabled()) {
    return new Response(null, { status: 404 });
  }

  let clearCurrentTransaction = true;
  let stage: 'callback' | 'core_handoff' | 'token_exchange' = 'callback';
  try {
    const validated = validateGoogleOidcCallback(
      request.nextUrl.searchParams,
      request.cookies.get(googleOidcTransactionCookieName())?.value,
    );
    stage = 'token_exchange';
    const exchange = await exchangeGoogleOidcAuthorizationCode(
      getGoogleOidcBffConfig(),
      validated.authorizationCode,
      validated.transaction,
    );
    stage = 'core_handoff';
    const handoff = await handoffGoogleOidcToCore(exchange, validated.transaction);
    if (handoff.status === 'AUTHENTICATED') {
      const response = redirect(validated.transaction.returnTo);
      clearGoogleTransaction(response);
      response.cookies.set(
        appSessionCookieName(),
        handoff.sessionToken,
        appSessionCookieOptions(appSessionMaxAge(handoff.idleExpiresAt, handoff.absoluteExpiresAt)),
      );
      response.cookies.set(googlePendingOnboardingCookieName(), '', {
        ...googlePendingOnboardingCookieOptions(),
        expires: new Date(0),
        maxAge: 0,
      });
      return response;
    }

    const pending = createGooglePendingOnboarding(handoff, validated.transaction);
    const response = redirect('/auth/google/complete');
    clearGoogleTransaction(response);
    response.cookies.set(
      googlePendingOnboardingCookieName(),
      serializeGooglePendingOnboarding(pending),
      googlePendingOnboardingCookieOptions(
        Math.max(1, Math.floor((pending.expiresAt - Date.now()) / 1000)),
      ),
    );
    return response;
  } catch (error) {
    if (error instanceof GoogleOidcCallbackError) {
      clearCurrentTransaction = error.clearCurrentTransaction;
      logAuthDiagnostic('Direct Google callback rejected', { reason: error.reason });
    } else {
      logAuthDiagnostic('Direct Google callback failed', { stage });
    }
    return failedCallback(clearCurrentTransaction);
  }
}
