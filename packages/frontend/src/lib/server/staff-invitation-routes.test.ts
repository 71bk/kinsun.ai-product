import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST as acceptInvitation } from '../../app/backend/staff-invitations/accept/route';

const handoffSecret = 'synthetic-kinsun-handoff-secret-material-32-bytes';
const token = `wi1_${'a'.repeat(43)}`;
const password = 'Synthetic-only-password-1';
const email = 'synthetic.worker@example.test';

function configure(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('KINSUN_NATIVE_AUTH_ENABLED', 'true');
  vi.stubEnv('KINSUN_AUTH_HANDOFF_SECRET', handoffSecret);
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
}

function acceptRequest(body: unknown, origin: string | null = 'http://localhost:3000'): NextRequest {
  return new NextRequest('http://localhost:3000/backend/staff-invitations/accept', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(origin ? { Origin: origin } : {}),
    },
    body: JSON.stringify(body),
  });
}

function activatedCoreResponse(): Response {
  return Response.json({ data: { status: 'ACTIVATED' }, meta: {} });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('staff invitation acceptance BFF route', () => {
  it('stays dark when native authentication is disabled', async () => {
    configure();
    vi.stubEnv('KINSUN_NATIVE_AUTH_ENABLED', 'false');
    const fetchMock = vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await acceptInvitation(
      acceptRequest({ email, password, invitation_token: token }),
    );

    expect(response.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a cross-origin post before reaching Core', async () => {
    configure();
    const fetchMock = vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await acceptInvitation(
      acceptRequest({ email, password, invitation_token: token }, 'http://attacker.example'),
    );

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('activates the account and never returns a session token', async () => {
    configure();
    const fetchMock = vi
      .fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>()
      .mockResolvedValue(activatedCoreResponse());
    vi.stubGlobal('fetch', fetchMock);

    const response = await acceptInvitation(
      acceptRequest({ email, password, invitation_token: token }),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: 'ACTIVATED' });
    expect(response.headers.get('set-cookie')).toBeNull();
    expect(response.headers.get('Cache-Control')).toBe('no-store');

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(sent.invitation_token).toBe(token);
    expect(sent.email).toBe(email);
  });

  it('never puts the credential in the URL it calls Core with', async () => {
    configure();
    const fetchMock = vi
      .fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>()
      .mockResolvedValue(activatedCoreResponse());
    vi.stubGlobal('fetch', fetchMock);

    await acceptInvitation(acceptRequest({ email, password, invitation_token: token }));

    const [target] = fetchMock.mock.calls[0] ?? [];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/internal/auth/staff-invitations/accept');
    expect(String(target)).not.toContain('wi1_');
  });

  it.each([
    ['a null body', null],
    ['an array body', []],
    ['a scalar body', 'invalid'],
    ['a malformed credential', { email, password, invitation_token: 'wi1_short' }],
    ['a credential from another scheme', { email, password, invitation_token: `ep1_${'a'.repeat(43)}` }],
    ['a password under the minimum length', { email, password: 'short', invitation_token: token }],
    ['an unusable email', { email: 'not-an-email', password, invitation_token: token }],
  ])('refuses %s without calling Core', async (_label, body) => {
    configure();
    const fetchMock = vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await acceptInvitation(acceptRequest(body));

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  /**
   * Core answers "spent", "expired", "revoked", "wrong email" and "feature off"
   * with deliberately indistinguishable rejections. If this route turned them
   * back into different statuses it would rebuild the oracle Core denies.
   */
  it.each([400, 401, 404, 409, 422, 500, 503])(
    'collapses a Core %i into a single opaque rejection',
    async (status) => {
      configure();
      vi.stubGlobal(
        'fetch',
        vi
          .fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>()
          .mockResolvedValue(new Response('{}', { status })),
      );

      const response = await acceptInvitation(
        acceptRequest({ email, password, invitation_token: token }),
      );

      expect(response.status).toBe(400);
      const body = (await response.json()) as { error?: { reason_code?: string } };
      expect(body.error?.reason_code).toBe('INVITATION_REJECTED');
    },
  );

  it('rejects a Core response that is not a bare activation receipt', async () => {
    configure();
    vi.stubGlobal(
      'fetch',
      vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>().mockResolvedValue(
        Response.json({
          data: { status: 'ACTIVATED', session_token: `ks1_${'b'.repeat(43)}` },
          meta: {},
        }),
      ),
    );

    const response = await acceptInvitation(
      acceptRequest({ email, password, invitation_token: token }),
    );

    expect(response.status).toBe(400);
  });
});
