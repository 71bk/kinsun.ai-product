import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DELETE as revokeAcknowledgement,
  POST as createAcknowledgement,
} from '../../app/backend/elder-session/acknowledgement/route';
import { POST as companionTurn } from '../../app/backend/elder-session/companion-turns/route';
import { DELETE as endSession, GET as currentSession } from '../../app/backend/elder-session/current/route';
import { POST as exchangePairing } from '../../app/backend/elder-session/exchange/route';
import { appSessionCookieName } from './app-session-cookie';
import { elderSessionCookieName } from './elder-session-cookie';

const PAIRING_TOKEN = `ep1_${'a'.repeat(43)}`;
const SESSION_TOKEN = `es1_${'b'.repeat(43)}`;

function configure(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
}

function request(
  path: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`, init);
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('assisted Elder Session BFF boundary', () => {
  it('exchanges pairing without returning es1 and clears any staff session', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-01T04:00:00Z'));
    const fetchMock = vi.fn(async () =>
      Response.json({
        data: {
          assisted_session_id: '79000000-0000-4000-8000-000000000001',
          elder_id: '75000000-0000-4000-8000-000000000001',
          display_name: 'Synthetic Elder',
          preferred_name: 'Synthetic',
          session_token: SESSION_TOKEN,
          idle_expires_at: '2026-09-01T04:30:00Z',
          absolute_expires_at: '2026-09-01T12:00:00Z',
        },
        meta: {},
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await exchangePairing(
      request('/backend/elder-session/exchange', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Origin: 'http://localhost:3000',
        },
        body: JSON.stringify({ pairing_token: PAIRING_TOKEN }),
      }),
    );

    expect(response.status).toBe(200);
    expect(await response.text()).not.toContain(SESSION_TOKEN);
    const cookies = response.headers.get('set-cookie') ?? '';
    expect(cookies).toContain(`${elderSessionCookieName()}=${SESSION_TOKEN}`);
    expect(cookies).toContain(`${appSessionCookieName()}=`);
    const [, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];
    expect(new Headers(init.headers).has('Authorization')).toBe(false);
  });

  it('rejects cross-origin exchange before contacting Core', async () => {
    configure();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await exchangePairing(
      request('/backend/elder-session/exchange', {
        method: 'POST',
        headers: { Origin: 'https://attacker.invalid' },
        body: JSON.stringify({ pairing_token: PAIRING_TOKEN }),
      }),
    );

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards only the cookie credential and server-selected current scope', async () => {
    configure();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe('http://127.0.0.1:8000/api/v1/assisted-elder-sessions/current');
      expect(new Headers(init?.headers).get('Authorization')).toBe(`Bearer ${SESSION_TOKEN}`);
      return Response.json({ data: { status: 'ACTIVE' }, meta: {} });
    });
    vi.stubGlobal('fetch', fetchMock);

    const response = await currentSession(
      request('/backend/elder-session/current', {
        headers: { Cookie: `${elderSessionCookieName()}=${SESSION_TOKEN}` },
      }),
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('drops client-supplied scope fields from companion turns', async () => {
    configure();
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(new Headers(init?.headers).get('Authorization')).toBe(`Bearer ${SESSION_TOKEN}`);
      expect(JSON.parse(String(init?.body))).toEqual({ input_text: 'Hello' });
      return Response.json({ data: { reply_text: 'Hi' }, meta: {} });
    });
    vi.stubGlobal('fetch', fetchMock);

    const response = await companionTurn(
      request('/backend/elder-session/companion-turns', {
        method: 'POST',
        headers: {
          Cookie: `${elderSessionCookieName()}=${SESSION_TOKEN}`,
          Origin: 'http://localhost:3000',
        },
        body: JSON.stringify({
          input_text: 'Hello',
          elder_id: 'client-must-not-select-this',
          tenant_id: 'client-must-not-select-this',
        }),
      }),
    );

    expect(response.status).toBe(200);
  });

  it('creates tablet acknowledgement from a server-selected payload only', async () => {
    configure();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(
        'http://127.0.0.1:8000/api/v1/assisted-elder-sessions/current/first-use-acknowledgement',
      );
      expect(new Headers(init?.headers).get('Authorization')).toBe(`Bearer ${SESSION_TOKEN}`);
      expect(JSON.parse(String(init?.body))).toEqual({ acknowledged: true });
      return Response.json({ data: { status: 'ACKNOWLEDGED' }, meta: {} });
    });
    vi.stubGlobal('fetch', fetchMock);

    const response = await createAcknowledgement(
      request('/backend/elder-session/acknowledgement', {
        method: 'POST',
        headers: {
          Cookie: `${elderSessionCookieName()}=${SESSION_TOKEN}`,
          Origin: 'http://localhost:3000',
        },
        body: JSON.stringify({
          acknowledged: false,
          policy_version: 'client-must-not-select-this',
          granted_by_actor_id: 'client-must-not-select-this',
        }),
      }),
    );

    expect(response.status).toBe(200);
  });

  it('revoke forwards no client-selected reason or deletion scope', async () => {
    configure();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(
        'http://127.0.0.1:8000/api/v1/assisted-elder-sessions/current/first-use-acknowledgement/revoke',
      );
      expect(init?.method).toBe('POST');
      expect(init?.body).toBeUndefined();
      return Response.json({ data: { status: 'REQUIRED' }, meta: {} });
    });
    vi.stubGlobal('fetch', fetchMock);

    const response = await revokeAcknowledgement(
      request('/backend/elder-session/acknowledgement', {
        method: 'DELETE',
        headers: {
          Cookie: `${elderSessionCookieName()}=${SESSION_TOKEN}`,
          Origin: 'http://localhost:3000',
        },
        body: JSON.stringify({ reason_code: 'client-must-not-select-this' }),
      }),
    );

    expect(response.status).toBe(200);
  });

  it('rejects cross-origin acknowledgement before contacting Core', async () => {
    configure();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await createAcknowledgement(
      request('/backend/elder-session/acknowledgement', {
        method: 'POST',
        headers: {
          Cookie: `${elderSessionCookieName()}=${SESSION_TOKEN}`,
          Origin: 'https://attacker.invalid',
        },
      }),
    );

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('revokes Core state before clearing the Elder Session cookie', async () => {
    configure();
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ data: { status: 'ENDED' }, meta: {} })));

    const response = await endSession(
      request('/backend/elder-session/current', {
        method: 'DELETE',
        headers: {
          Cookie: `${elderSessionCookieName()}=${SESSION_TOKEN}`,
          Origin: 'http://localhost:3000',
        },
      }),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get('set-cookie')).toContain(`${elderSessionCookieName()}=`);
    expect(response.headers.get('set-cookie')).toContain('Max-Age=0');
  });
});
