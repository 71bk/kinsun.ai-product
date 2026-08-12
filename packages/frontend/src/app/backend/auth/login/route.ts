import { NextRequest, NextResponse } from 'next/server';
import { isTrustedRequestOrigin } from '@/lib/server/auth-cookie';
import { bffError } from '@/lib/server/bff-response';
import { buildCognitoAuthorizationUrl, getCognitoOAuthConfig } from '@/lib/server/cognito-oauth';
import {
  buildGoogleOidcAuthorizationUrl,
  getGoogleOidcBffConfig,
  googleDirectOidcEnabled,
} from '@/lib/server/google-oidc';
import {
  googleOidcCoreAuthorization,
  googleOidcCoreTarget,
} from '@/lib/server/google-oidc-core-handoff';
import {
  createGoogleOidcTransaction,
  googleOidcTransactionCookieName,
  googleOidcTransactionCookieOptions,
  serializeGoogleOidcTransaction,
} from '@/lib/server/google-oidc-transaction';
import {
  buildLineLoginLinkAuthorizationUrl,
  getLineLoginOAuthConfig,
  lineDirectOidcEnabled,
} from '@/lib/server/line-login-oauth';
import { lineOidcCoreAuthorization, lineOidcCoreTarget } from '@/lib/server/line-oidc-core-handoff';
import {
  createLineOidcTransaction,
  lineOidcTransactionCookieName,
  lineOidcTransactionCookieOptions,
  serializeLineOidcTransaction,
} from '@/lib/server/line-oidc-transaction';
import {
  createOAuthTransaction,
  loginProvider,
  normalizeInvitationCode,
  onboardingIntent,
  oauthTransactionCookieName,
  oauthTransactionCookieOptions,
  serializeOAuthTransaction,
  strictRelativeReturnTo,
} from '@/lib/server/oauth-transaction';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function noStore(response: NextResponse): NextResponse {
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
}

function beginLogin(
  rawReturnTo: string | null,
  rawIntent: unknown,
  rawInvitationCode: unknown,
  rawProvider: unknown,
): Response {
  const returnTo = strictRelativeReturnTo(rawReturnTo);
  const intent = onboardingIntent(rawIntent);
  const invitationCode = normalizeInvitationCode(rawInvitationCode);
  const provider = loginProvider(rawProvider);
  if (returnTo === null) {
    return bffError(400, 'bad_request', 'Invalid sign-in return path', 'INVALID_RETURN_TO');
  }
  if (
    !intent ||
    !provider ||
    invitationCode === null ||
    (intent !== 'FAMILY' && invitationCode !== undefined)
  ) {
    return bffError(400, 'bad_request', 'Invalid sign-in request', 'INVALID_SIGN_IN_REQUEST');
  }

  try {
    if (provider === 'GOOGLE' && googleDirectOidcEnabled()) {
      // Fail before redirecting the user to Google if the callback could not
      // complete its private Core handoff in this deployment.
      googleOidcCoreTarget();
      googleOidcCoreAuthorization();
      const transaction = createGoogleOidcTransaction(returnTo, intent, invitationCode);
      const response = noStore(
        NextResponse.redirect(
          buildGoogleOidcAuthorizationUrl(getGoogleOidcBffConfig(), transaction),
          { status: 303 },
        ),
      );
      response.cookies.set(
        googleOidcTransactionCookieName(),
        serializeGoogleOidcTransaction(transaction),
        googleOidcTransactionCookieOptions(),
      );
      return response;
    }
    if (provider === 'LINE' && lineDirectOidcEnabled()) {
      lineOidcCoreTarget();
      lineOidcCoreAuthorization();
      const transaction = createLineOidcTransaction(returnTo, intent, invitationCode);
      const response = noStore(
        NextResponse.redirect(
          buildLineLoginLinkAuthorizationUrl(getLineLoginOAuthConfig('login'), transaction),
          { status: 303 },
        ),
      );
      response.cookies.set(
        lineOidcTransactionCookieName(),
        serializeLineOidcTransaction(transaction),
        lineOidcTransactionCookieOptions(),
      );
      return response;
    }
    const transaction = createOAuthTransaction(returnTo, intent, invitationCode, provider);
    const response = noStore(
      NextResponse.redirect(buildCognitoAuthorizationUrl(getCognitoOAuthConfig(), transaction), {
        status: 303,
      }),
    );
    response.cookies.set(
      oauthTransactionCookieName(),
      serializeOAuthTransaction(transaction),
      oauthTransactionCookieOptions(),
    );
    return response;
  } catch {
    return bffError(
      503,
      'service_unavailable',
      'Sign-in is temporarily unavailable',
      'AUTH_CONFIGURATION_UNAVAILABLE',
      true,
    );
  }
}

export async function POST(request: NextRequest): Promise<Response> {
  if (!isTrustedRequestOrigin(request)) {
    return bffError(403, 'forbidden', 'Request origin rejected', 'CSRF_ORIGIN_REJECTED');
  }
  if (
    !request.headers
      .get('content-type')
      ?.toLowerCase()
      .startsWith('application/x-www-form-urlencoded')
  ) {
    return bffError(415, 'unsupported_media_type', 'Form request required', 'FORM_REQUIRED');
  }
  const form = await request.formData().catch(() => null);
  if (!form) {
    return bffError(400, 'bad_request', 'Invalid sign-in request', 'INVALID_SIGN_IN_REQUEST');
  }
  return beginLogin(
    typeof form.get('returnTo') === 'string' ? String(form.get('returnTo')) : null,
    form.get('intent'),
    form.get('invitationCode'),
    form.get('provider'),
  );
}
