import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET as googleCallback } from '../../app/backend/auth/google/callback/route';
import { POST as completeGoogleOnboarding } from '../../app/backend/auth/google/onboarding/route';
import { POST as logout } from '../../app/backend/auth/logout/route';
import { appSessionCookieName } from './app-session-cookie';
import { accessTokenCookieName } from './auth-cookie';
import {
  createGooglePendingOnboarding,
  googlePendingOnboardingCookieName,
  parseGooglePendingOnboarding,
  serializeGooglePendingOnboarding,
} from './google-pending-onboarding';
import {
  createGoogleOidcTransaction,
  googleOidcTransactionCookieName,
  serializeGoogleOidcTransaction,
} from './google-oidc-transaction';

function configure(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('GOOGLE_DIRECT_OIDC_ENABLED', 'true');
  vi.stubEnv('GOOGLE_OIDC_CLIENT_ID', 'synthetic-google-client-id');
  vi.stubEnv('GOOGLE_OIDC_CLIENT_SECRET', 'synthetic-google-client-secret');
  vi.stubEnv(
    'GOOGLE_OIDC_TRANSACTION_SECRET',
    'synthetic-google-transaction-secret-material-32-bytes',
  );
  vi.stubEnv('GOOGLE_OIDC_HANDOFF_SECRET', 'synthetic-google-handoff-secret-material-32-bytes');
  vi.stubEnv('COGNITO_OAUTH_TRANSACTION_SECRET', 'independent-cognito-secret-32-bytes');
  vi.stubEnv('LINE_LOGIN_LINK_TRANSACTION_SECRET', 'independent-line-secret-32-bytes');
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

function idToken(nonce: string): string {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ nonce })).toString('base64url');
  return `${header}.${payload}.synthetic-signature`;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('direct Google authentication routes', () => {
  it('sets only the Core App Session after an existing-identity callback', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-12T00:00:00Z'));
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const target = String(input);
      if (target === 'https://oauth2.googleapis.com/token') {
        return Response.json({ id_token: idToken(transaction.nonce) });
      }
      return Response.json({
        data: {
          status: 'AUTHENTICATED',
          session_token: `ks1_${'a'.repeat(43)}`,
          idle_expires_at: '2026-08-19T00:00:00Z',
          absolute_expires_at: '2026-09-11T00:00:00Z',
        },
        meta: {},
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const response = await googleCallback(
      request(
        `/backend/auth/google/callback?code=synthetic-code&state=${transaction.state}&iss=${encodeURIComponent('https://accounts.google.com')}`,
        {
          headers: {
            Cookie: `${googleOidcTransactionCookieName()}=${serializeGoogleOidcTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/onboarding/resolve');
    expect(cookieValue(response, appSessionCookieName())).toBe(`ks1_${'a'.repeat(43)}`);
    expect(cookieValue(response, googleOidcTransactionCookieName())).toBe('');
    expect(cookieValue(response, accessTokenCookieName())).toBe('');
    expect(await response.text()).not.toContain(`ks1_${'a'.repeat(43)}`);
  });

  it('stores a signed short-lived pending credential for explicit onboarding', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-12T00:00:00Z'));
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        String(input) === 'https://oauth2.googleapis.com/token'
          ? Response.json({ id_token: idToken(transaction.nonce) })
          : Response.json({
              data: {
                status: 'PENDING',
                pending_token: `kp1_${'b'.repeat(43)}`,
                expires_at: '2026-08-12T00:10:00Z',
              },
              meta: {},
            }),
      ),
    );

    const response = await googleCallback(
      request(
        `/backend/auth/google/callback?code=synthetic-code&state=${transaction.state}&iss=${encodeURIComponent('https://accounts.google.com')}`,
        {
          headers: {
            Cookie: `${googleOidcTransactionCookieName()}=${serializeGoogleOidcTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.headers.get('location')).toBe('/auth/google/complete');
    const pending = parseGooglePendingOnboarding(
      cookieValue(response, googlePendingOnboardingCookieName()),
    );
    expect(pending).toMatchObject({
      intent: 'ELDER',
      pendingToken: `kp1_${'b'.repeat(43)}`,
      returnTo: '/onboarding/resolve',
    });
    expect(cookieValue(response, appSessionCookieName())).toBeUndefined();
  });

  it('completes pending onboarding and replaces legacy credentials', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-12T00:00:00Z'));
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const pending = createGooglePendingOnboarding(
      {
        status: 'PENDING',
        pendingToken: `kp1_${'b'.repeat(43)}`,
        expiresAt: '2026-08-12T00:10:00Z',
      },
      transaction,
    );
    const fetchMock = vi.fn(async () =>
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
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await completeGoogleOnboarding(
      request('/backend/auth/google/onboarding', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Cookie: `${googlePendingOnboardingCookieName()}=${serializeGooglePendingOnboarding(pending)}; ${accessTokenCookieName()}=legacy-token`,
          Origin: 'http://localhost:3000',
        },
        body: new URLSearchParams({ displayName: '合成長者' }),
      }),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/onboarding/resolve');
    expect(cookieValue(response, appSessionCookieName())).toBe(`ks1_${'c'.repeat(43)}`);
    expect(cookieValue(response, googlePendingOnboardingCookieName())).toBe('');
    expect(cookieValue(response, accessTokenCookieName())).toBe('');
  });

  it('revokes the Core session before clearing the direct-login cookie', async () => {
    configure();
    const token = `ks1_${'d'.repeat(43)}`;
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      Response.json({ data: { status: 'SIGNED_OUT' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await logout(
      request('/backend/auth/logout', {
        method: 'POST',
        headers: {
          Cookie: `${appSessionCookieName()}=${token}`,
          Origin: 'http://localhost:3000',
        },
      }),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/sign-in');
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.get('Authorization')).toBe(`Bearer ${token}`);
    expect(cookieValue(response, appSessionCookieName())).toBe('');
  });
});
