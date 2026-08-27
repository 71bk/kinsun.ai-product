import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST as completeRegistration } from '../../app/backend/auth/kinsun/complete/route';
import { POST as passwordLogin } from '../../app/backend/auth/kinsun/login/route';
import { POST as startRegistration } from '../../app/backend/auth/kinsun/start/route';
import { appSessionCookieName } from './app-session-cookie';
import {
  kinsunChallengeCookieName,
  kinsunReturnToCookieName,
} from './kinsun-auth-cookie';

const handoffSecret = 'synthetic-kinsun-handoff-secret-material-32-bytes';
const password = 'Synthetic-only-password-1';

function configure(): void {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-08-17T10:00:00Z'));
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

function authenticatedCoreResponse(sessionCharacter: string): Response {
  return Response.json({
    data: {
      status: 'AUTHENTICATED',
      session_token: `ks1_${sessionCharacter.repeat(43)}`,
      idle_expires_at: '2026-08-24T10:00:00Z',
      absolute_expires_at: '2026-09-16T10:00:00Z',
    },
    meta: {},
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Kinsun Email and password BFF routes', () => {
  it('keeps the feature dark when native authentication is disabled', async () => {
    vi.stubEnv('KINSUN_NATIVE_AUTH_ENABLED', 'false');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await passwordLogin(
      formRequest(
        '/backend/auth/kinsun/login',
        new URLSearchParams({
          email: 'synthetic.elder@example.test',
          password,
          returnTo: '/onboarding/resolve',
        }),
      ),
    );

    expect(response.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('starts registration through the private Core boundary without reflecting Email', async () => {
    configure();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      Response.json({
        data: {
          status: 'CHALLENGE_CREATED',
          challenge_token: `ke1_${'a'.repeat(43)}`,
          expires_at: '2026-08-17T10:10:00Z',
        },
        meta: {},
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await startRegistration(
      formRequest(
        '/backend/auth/kinsun/start',
        new URLSearchParams({
          email: 'synthetic.elder@example.test',
          displayName: '合成長者',
          intent: 'ELDER',
          returnTo: '/onboarding/resolve',
        }),
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/auth/kinsun/verify');
    expect(cookieValue(response, kinsunChallengeCookieName())).toBe(`ke1_${'a'.repeat(43)}`);
    expect(await response.text()).not.toContain('synthetic.elder@example.test');
    const [target, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/internal/auth/kinsun/email/start');
    expect(new Headers(init?.headers).get('X-Kinsun-BFF-Authorization')).toBe(
      `Bearer ${handoffSecret}`,
    );
  });

  it('completes registration and exposes the App Session only as an HttpOnly cookie', async () => {
    configure();
    const fetchMock = vi.fn(async () => authenticatedCoreResponse('b'));
    vi.stubGlobal('fetch', fetchMock);

    const response = await completeRegistration(
      formRequest(
        '/backend/auth/kinsun/complete',
        new URLSearchParams({
          verificationCode: '246810',
          password,
          passwordConfirmation: password,
        }),
        `${kinsunChallengeCookieName()}=ke1_${'a'.repeat(43)}; ${kinsunReturnToCookieName()}=/onboarding/resolve`,
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/onboarding/resolve');
    expect(cookieValue(response, appSessionCookieName())).toBe(`ks1_${'b'.repeat(43)}`);
    const body = await response.text();
    expect(body).not.toContain(password);
    expect(body).not.toContain(`ks1_${'b'.repeat(43)}`);
  });

  it('logs in through the private Core boundary and never puts credentials in the response body', async () => {
    configure();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      authenticatedCoreResponse('c'),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await passwordLogin(
      formRequest(
        '/backend/auth/kinsun/login',
        new URLSearchParams({
          email: 'synthetic.elder@example.test',
          password,
          returnTo: '/onboarding/resolve',
        }),
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/onboarding/resolve');
    expect(cookieValue(response, appSessionCookieName())).toBe(`ks1_${'c'.repeat(43)}`);
    expect(await response.text()).not.toContain(password);
    const [target, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(target)).toBe(
      'http://127.0.0.1:8000/api/v1/internal/auth/kinsun/password/login',
    );
    expect(new Headers(init?.headers).get('X-Kinsun-BFF-Authorization')).toBe(
      `Bearer ${handoffSecret}`,
    );
  });

  it('maps every Core authentication rejection to the same browser-visible failure', async () => {
    configure();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json(
          {
            error: {
              code: 'authentication_required',
              message: 'Authentication required.',
            },
          },
          { status: 401 },
        ),
      ),
    );

    const response = await passwordLogin(
      formRequest(
        '/backend/auth/kinsun/login',
        new URLSearchParams({
          email: 'missing.account@example.test',
          password,
          returnTo: '/onboarding/resolve',
        }),
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/sign-in?error=invalid_credentials');
    expect(cookieValue(response, appSessionCookieName())).toBeUndefined();
    const body = await response.text();
    expect(body).not.toContain('missing.account@example.test');
    expect(body).not.toContain(password);
  });
});
