import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST as beginLogin } from '../../app/backend/auth/login/route';
import { GET as lineCallback } from '../../app/backend/auth/line/callback/route';
import { POST as completeLineOnboarding } from '../../app/backend/auth/line/onboarding/route';
import { appSessionCookieName } from './app-session-cookie';
import { accessTokenCookieName } from './auth-cookie';
import {
  createLineOidcTransaction,
  lineOidcTransactionCookieName,
  serializeLineOidcTransaction,
} from './line-oidc-transaction';
import {
  createLinePendingOnboarding,
  linePendingOnboardingCookieName,
  parseLinePendingOnboarding,
  serializeLinePendingOnboarding,
} from './line-pending-onboarding';

function configure(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('LINE_DIRECT_OIDC_ENABLED', 'true');
  vi.stubEnv('LINE_LOGIN_CHANNEL_ID', '1234567890');
  vi.stubEnv('LINE_LOGIN_CHANNEL_SECRET', 'synthetic-line-channel-secret');
  vi.stubEnv('LINE_OIDC_CALLBACK_URL', 'http://localhost:3000/backend/auth/line/callback');
  vi.stubEnv('LINE_OIDC_TRANSACTION_SECRET', 'synthetic-line-transaction-secret-material-32-bytes');
  vi.stubEnv('LINE_OIDC_HANDOFF_SECRET', 'synthetic-line-handoff-secret-material-32-bytes');
  vi.stubEnv('LINE_LOGIN_LINK_TRANSACTION_SECRET', 'independent-line-link-secret-32-bytes');
  vi.stubEnv('LINE_CHANNEL_SECRET', 'independent-line-messaging-secret');
  vi.stubEnv('GOOGLE_OIDC_TRANSACTION_SECRET', 'independent-google-transaction-secret-32-bytes');
  vi.stubEnv('GOOGLE_OIDC_HANDOFF_SECRET', 'independent-google-handoff-secret-32-bytes');
  vi.stubEnv('FAMILY_INVITATION_HMAC_SECRET', 'independent-family-secret-material-32-bytes');
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
}

function request(
  path: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`, init);
}

function cookieValue(response: Response, name: string): string | undefined {
  const header = response.headers.get('set-cookie') ?? '';
  return new RegExp(`(?:^|, )${name}=([^;]*)`).exec(header)?.[1];
}

function verifiedClaims(nonce: string) {
  return {
    iss: 'https://access.line.me',
    sub: 'U1234567890abcdef',
    aud: '1234567890',
    exp: Math.floor(Date.now() / 1000) + 300,
    iat: Math.floor(Date.now() / 1000) - 5,
    nonce,
    name: 'LINE User',
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('direct LINE authentication routes', () => {
  it('starts LINE authorization with PKCE and a signed transaction', async () => {
    configure();
    const response = await beginLogin(
      request('/backend/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: 'http://localhost:3000',
        },
        body: new URLSearchParams({
          intent: 'ELDER',
          provider: 'LINE',
          returnTo: '/onboarding/resolve',
        }),
      }),
    );

    expect(response.status).toBe(303);
    const location = new URL(response.headers.get('location') ?? '');
    expect(location.origin).toBe('https://access.line.me');
    expect(location.searchParams.get('client_id')).toBe('1234567890');
    expect(location.searchParams.get('redirect_uri')).toBe(
      'http://localhost:3000/backend/auth/line/callback',
    );
    expect(location.searchParams.get('code_challenge_method')).toBe('S256');
    expect(cookieValue(response, lineOidcTransactionCookieName())).toBeTruthy();
  });

  it('sets a Core App Session and revokes the temporary LINE token', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-12T00:00:00Z'));
    const transaction = createLineOidcTransaction('/onboarding/resolve', 'ELDER');
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const target = String(input);
      if (target === 'https://api.line.me/oauth2/v2.1/token') {
        return Response.json({
          access_token: 'temporary-line-access-token',
          id_token: 'header.payload.signature',
        });
      }
      if (target === 'https://api.line.me/oauth2/v2.1/verify') {
        return Response.json(verifiedClaims(transaction.nonce));
      }
      if (target === 'http://127.0.0.1:8000/api/v1/internal/auth/line/handoff') {
        return Response.json({
          data: {
            status: 'AUTHENTICATED',
            session_token: `ks1_${'a'.repeat(43)}`,
            idle_expires_at: '2026-08-19T00:00:00Z',
            absolute_expires_at: '2026-09-11T00:00:00Z',
          },
          meta: {},
        });
      }
      if (target === 'https://api.line.me/oauth2/v2.1/revoke') {
        return new Response(null, { status: 200 });
      }
      throw new Error(`Unexpected target: ${target}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const response = await lineCallback(
      request(`/backend/auth/line/callback?code=synthetic-code&state=${transaction.state}`, {
        headers: {
          Cookie: `${lineOidcTransactionCookieName()}=${serializeLineOidcTransaction(transaction)}`,
        },
      }),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/onboarding/resolve');
    expect(cookieValue(response, appSessionCookieName())).toBe(`ks1_${'a'.repeat(43)}`);
    expect(cookieValue(response, lineOidcTransactionCookieName())).toBe('');
    expect(cookieValue(response, accessTokenCookieName())).toBe('');
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(await response.text()).not.toContain('temporary-line-access-token');
  });

  it('stores and completes a signed LINE pending onboarding transaction', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-12T00:00:00Z'));
    const transaction = createLineOidcTransaction('/onboarding/resolve', 'ELDER');
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const target = String(input);
      if (target === 'https://api.line.me/oauth2/v2.1/token') {
        return Response.json({
          access_token: 'temporary-token',
          id_token: 'header.payload.signature',
        });
      }
      if (target === 'https://api.line.me/oauth2/v2.1/verify') {
        return Response.json(verifiedClaims(transaction.nonce));
      }
      if (target === 'http://127.0.0.1:8000/api/v1/internal/auth/line/handoff') {
        return Response.json({
          data: {
            status: 'PENDING',
            pending_token: `kp1_${'b'.repeat(43)}`,
            expires_at: '2026-08-12T00:10:00Z',
          },
          meta: {},
        });
      }
      return new Response(null, { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const callbackResponse = await lineCallback(
      request(`/backend/auth/line/callback?code=synthetic-code&state=${transaction.state}`, {
        headers: {
          Cookie: `${lineOidcTransactionCookieName()}=${serializeLineOidcTransaction(transaction)}`,
        },
      }),
    );
    expect(callbackResponse.headers.get('location')).toBe('/auth/line/complete');
    const pending = parseLinePendingOnboarding(
      cookieValue(callbackResponse, linePendingOnboardingCookieName()),
    );
    expect(pending?.pendingToken).toBe(`kp1_${'b'.repeat(43)}`);

    const completedPending = createLinePendingOnboarding(
      {
        status: 'PENDING',
        pendingToken: `kp1_${'b'.repeat(43)}`,
        expiresAt: '2026-08-12T00:10:00Z',
      },
      transaction,
    );
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          data: {
            status: 'ACTIVE',
            intent: 'ELDER',
            actor_id: '20000000-0000-4000-8000-000000000001',
            tenant_id: '10000000-0000-4000-8000-000000000001',
            elder_id: '30000000-0000-4000-8000-000000000001',
            session_token: `ks1_${'c'.repeat(43)}`,
            idle_expires_at: '2026-08-19T00:00:00Z',
            absolute_expires_at: '2026-09-11T00:00:00Z',
          },
          meta: {},
        }),
      ),
    );

    const response = await completeLineOnboarding(
      request('/backend/auth/line/onboarding', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Cookie: `${linePendingOnboardingCookieName()}=${serializeLinePendingOnboarding(completedPending)}`,
          Origin: 'http://localhost:3000',
        },
        body: new URLSearchParams({ displayName: 'LINE User' }),
      }),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/onboarding/resolve');
    expect(cookieValue(response, appSessionCookieName())).toBe(`ks1_${'c'.repeat(43)}`);
    expect(cookieValue(response, linePendingOnboardingCookieName())).toBe('');
  });
});
