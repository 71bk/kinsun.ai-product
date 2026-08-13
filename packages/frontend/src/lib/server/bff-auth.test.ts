import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { appSessionCookieName, appSessionCookieOptions } from './app-session-cookie';
import { proxyCoreRequest } from './core-proxy';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function request(
  path: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
): NextRequest {
  return new NextRequest(`http://localhost${path}`, init);
}

describe('HttpOnly authentication session', () => {
  it('uses a Secure host-only App Session cookie in production', () => {
    vi.stubEnv('NODE_ENV', 'production');

    expect(appSessionCookieName()).toBe('__Host-kinsun_session');
    expect(appSessionCookieOptions()).toMatchObject({
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      path: '/',
    });
  });
});

describe('Core BFF proxy', () => {
  it('forwards a valid App Session as the Core bearer credential', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
    const token = `ks1_${'a'.repeat(43)}`;
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      Response.json({ data: {}, meta: {} }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(
      request('/backend/core/api/v1/me', {
        headers: { Cookie: `kinsun_session=${token}` },
      }),
      ['api', 'v1', 'me'],
    );

    expect(response.status).toBe(200);
    const [target, init] = fetchMock.mock.calls[0];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/me');
    const headers = new Headers(init?.headers);
    expect(headers.get('Authorization')).toBe(`Bearer ${token}`);
    expect(headers.has('Cookie')).toBe(false);
  });

  it('fails closed before contacting Core when the cookie is missing', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(request('/backend/core/api/v1/example'), [
      'api',
      'v1',
      'example',
    ]);

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fails closed when the credential cookie is malformed', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(
      request('/backend/core/api/v1/example', {
        headers: { Cookie: 'kinsun_session=malformed' },
      }),
      ['api', 'v1', 'example'],
    );

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects cross-origin state changes', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(
      request('/backend/core/api/v1/example', {
        method: 'POST',
        headers: {
          Cookie: `kinsun_session=ks1_${'a'.repeat(43)}`,
          Origin: 'https://attacker.example',
          'Content-Type': 'application/json',
        },
        body: '{}',
      }),
      ['api', 'v1', 'example'],
    );

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects credentials in a proxied query string', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyCoreRequest(
      request('/backend/core/api/v1/example?access_token=leak', {
        headers: { Cookie: `kinsun_session=ks1_${'a'.repeat(43)}` },
      }),
      ['api', 'v1', 'example'],
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
