import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST as completeRegistration } from '../../app/backend/auth/kinsun/complete/route';
import { POST as passwordLogin } from '../../app/backend/auth/kinsun/login/route';
import { POST as startRegistration } from '../../app/backend/auth/kinsun/start/route';
import { appSessionCookieName } from './app-session-cookie';
import {
  kinsunChallengeCookieName,
  kinsunInvitationCookieName,
  kinsunReturnToCookieName,
} from './kinsun-auth-cookie';

const handoffSecret = 'synthetic-kinsun-handoff-secret-material-32-bytes';

function configure(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('KINSUN_NATIVE_AUTH_ENABLED', 'true');
  vi.stubEnv('KINSUN_AUTH_HANDOFF_SECRET', handoffSecret);
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
}

function request(
  path: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`, init);
}

function formRequest(path: string, body: URLSearchParams, cookie?: string): NextRequest {
  return request(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Origin: 'http://localhost:3000',
      ...(cookie ? { Cookie: cookie } : {}),
    },
    body,
  });
}

function cookieValue(response: Response, name: string): string | undefined {
  const header = response.headers.get('set-cookie') ?? '';
  return new RegExp(`(?:^|, )${name}=([^;]*)`).exec(header)?.[1];
}

function authenticatedEnvelope() {
  return {
    data: {
      status: 'AUTHENTICATED',
      session_token: `ks1_${'s'.repeat(43)}`,
      idle_expires_at: '2026-08-21T10:00:00Z',
      absolute_expires_at: '2026-09-13T10:00:00Z',
    },
    meta: {},
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Kinsun email and password authentication routes', () => {
  it('fails closed when the feature gate is disabled', async () => {
    configure();
    vi.stubEnv('KINSUN_NATIVE_AUTH_ENABLED', 'false');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await passwordLogin(
      formRequest(
        '/backend/auth/kinsun/login',
        new URLSearchParams({
          email: 'synthetic.elder@example.com',
          password: 'synthetic-password',
          returnTo: '/onboarding/resolve',
        }),
      ),
    );

    expect(response.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('starts registration through the dedicated secret and stores only bounded state', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-14T10:00:00Z'));
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json({
          data: {
            status: 'CHALLENGE_CREATED',
            challenge_token: `ke1_${'c'.repeat(43)}`,
            expires_at: '2026-08-14T10:10:00Z',
          },
          meta: {},
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await startRegistration(
      formRequest(
        '/backend/auth/kinsun/start',
        new URLSearchParams({
          email: ' Synthetic.Elder@Example.COM ',
          displayName: '合成長者',
          intent: 'ELDER',
          returnTo: '/onboarding/resolve',
        }),
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/auth/kinsun/verify');
    expect(cookieValue(response, kinsunChallengeCookieName())).toBe(`ke1_${'c'.repeat(43)}`);
    expect(cookieValue(response, kinsunReturnToCookieName())).toBe('%2Fonboarding%2Fresolve');
    expect(response.headers.get('set-cookie')).toContain('HttpOnly');
    const [target, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/internal/auth/kinsun/email/start');
    expect(init).toMatchObject({ cache: 'no-store', method: 'POST', redirect: 'error' });
    expect(init?.headers).toMatchObject({
      'X-Kinsun-BFF-Authorization': `Bearer ${handoffSecret}`,
    });
    expect(JSON.parse(String(init?.body))).toEqual({
      email: 'synthetic.elder@example.com',
      intent: 'ELDER',
      display_name: '合成長者',
    });
  });

  it('rejects cross-site, malformed email, and invitation-less family starts before Core', async () => {
    configure();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const base = {
      intent: 'FAMILY',
      returnTo: '/onboarding/resolve',
      email: 'synthetic.family@example.com',
    };

    const crossSite = await startRegistration(
      request('/backend/auth/kinsun/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: 'https://attacker.example',
        },
        body: new URLSearchParams(base),
      }),
    );
    const invalidFamily = await startRegistration(
      formRequest('/backend/auth/kinsun/start', new URLSearchParams(base)),
    );
    const malformedEmail = await startRegistration(
      formRequest(
        '/backend/auth/kinsun/start',
        new URLSearchParams({ ...base, intent: 'ELDER', email: 'not-an-email' }),
      ),
    );

    expect(crossSite.status).toBe(403);
    expect(invalidFamily.headers.get('location')).toBe('/sign-in?error=invalid_request');
    expect(malformedEmail.headers.get('location')).toBe('/sign-in?error=invalid_request');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('completes registration, rotates to one App Session, and clears challenge state', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-14T10:00:00Z'));
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json(authenticatedEnvelope()),
    );
    vi.stubGlobal('fetch', fetchMock);
    const challenge = `ke1_${'c'.repeat(43)}`;
    const cookies = [
      `${kinsunChallengeCookieName()}=${challenge}`,
      `${kinsunReturnToCookieName()}=${encodeURIComponent('/onboarding/resolve')}`,
    ].join('; ');

    const response = await completeRegistration(
      formRequest(
        '/backend/auth/kinsun/complete',
        new URLSearchParams({
          verificationCode: '246810',
          password: 'synthetic-password',
          passwordConfirmation: 'synthetic-password',
        }),
        cookies,
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/onboarding/resolve');
    expect(cookieValue(response, appSessionCookieName())).toBe(`ks1_${'s'.repeat(43)}`);
    expect(cookieValue(response, kinsunChallengeCookieName())).toBe('');
    expect(cookieValue(response, kinsunInvitationCookieName())).toBe('');
    expect(cookieValue(response, kinsunReturnToCookieName())).toBe('');
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(JSON.parse(String(init?.body))).toEqual({
      challenge_token: challenge,
      verification_code: '246810',
      password: 'synthetic-password',
    });
  });

  it('requires a form content type and matching password before completion', async () => {
    configure();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const wrongType = await completeRegistration(
      request('/backend/auth/kinsun/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Origin: 'http://localhost:3000' },
        body: '{}',
      }),
    );
    const mismatch = await completeRegistration(
      formRequest(
        '/backend/auth/kinsun/complete',
        new URLSearchParams({
          verificationCode: '246810',
          password: 'synthetic-password',
          passwordConfirmation: 'different-password',
        }),
      ),
    );

    expect(wrongType.status).toBe(415);
    expect(mismatch.headers.get('location')).toBe('/auth/kinsun/verify?error=invalid');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('logs only rejection status and keeps password failures indistinguishable', async () => {
    configure();
    const email = 'unknown.elder@example.com';
    const password = 'restricted-password';
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async (): Promise<Response> => new Response('restricted upstream body', { status: 401 }),
      ),
    );

    const response = await passwordLogin(
      formRequest(
        '/backend/auth/kinsun/login',
        new URLSearchParams({ email, password, returnTo: '/onboarding/resolve' }),
      ),
    );

    expect(response.headers.get('location')).toBe('/sign-in?error=invalid_credentials');
    expect(cookieValue(response, appSessionCookieName())).toBeUndefined();
    expect(errorSpy).toHaveBeenCalledWith(
      '[auth] Core Kinsun authentication rejected {"status":401}',
    );
    const log = JSON.stringify(errorSpy.mock.calls);
    expect(log).not.toContain(email);
    expect(log).not.toContain(password);
    expect(log).not.toContain(handoffSecret);
  });

  it('fails closed for a credentialed Core URL or a reused handoff secret', async () => {
    configure();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const body = new URLSearchParams({
      email: 'synthetic.elder@example.com',
      password: 'synthetic-password',
      returnTo: '/onboarding/resolve',
    });

    vi.stubEnv('CORE_API_INTERNAL_URL', 'https://user:password@attacker.example');
    const unsafeUrl = await passwordLogin(
      formRequest('/backend/auth/kinsun/login', new URLSearchParams(body)),
    );

    vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
    vi.stubEnv('GOOGLE_OIDC_HANDOFF_SECRET', handoffSecret);
    const reusedSecret = await passwordLogin(
      formRequest('/backend/auth/kinsun/login', new URLSearchParams(body)),
    );

    expect(unsafeUrl.headers.get('location')).toBe('/sign-in?error=auth_unavailable');
    expect(reusedSecret.headers.get('location')).toBe('/sign-in?error=auth_unavailable');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects Core responses that contain undeclared identity data', async () => {
    configure();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (): Promise<Response> => {
        const envelope = authenticatedEnvelope();
        return Response.json({
          ...envelope,
          data: { ...envelope.data, email: 'must-not-cross-the-boundary@example.com' },
        });
      }),
    );

    const response = await passwordLogin(
      formRequest(
        '/backend/auth/kinsun/login',
        new URLSearchParams({
          email: 'synthetic.elder@example.com',
          password: 'synthetic-password',
          returnTo: '/onboarding/resolve',
        }),
      ),
    );

    expect(response.headers.get('location')).toBe('/sign-in?error=auth_unavailable');
    expect(cookieValue(response, appSessionCookieName())).toBeUndefined();
  });
});
