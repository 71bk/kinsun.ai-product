import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { POST } from '../../app/backend/elder-session/voice/[...path]/route';
import { elderSessionCookieName } from './elder-session-cookie';

const sessionId = '75000000-0000-4000-8000-000000000001';
const token = `es1_${'a'.repeat(43)}`;
beforeEach(() => {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
function request(body: unknown, origin = 'http://localhost:3000', cookie = `${elderSessionCookieName()}=${token}`) {
  return new NextRequest('http://localhost:3000/backend/elder-session/voice/tickets', {
    method: 'POST', headers: { Origin: origin, Cookie: cookie, Authorization: 'Bearer malicious', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
it('accepts only the tablet cookie and exact allowlisted Core path', async () => {
  const fetchMock = vi.fn<[RequestInfo | URL, RequestInit?], Promise<Response>>(async () => Response.json({ data: {}, meta: {} }));
  vi.stubGlobal('fetch', fetchMock);
  const result = await POST(request({ input_text: '今天想聊天' }), { params: Promise.resolve({ path: [sessionId, 'turns'] }) });
  expect(result.status).toBe(200);
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toBe(`http://127.0.0.1:8000/api/v1/assisted-elder-sessions/current/voice-sessions/${sessionId}/companion-turns`);
  expect(new Headers(init?.headers).get('Authorization')).toBe(`Bearer ${token}`);
  expect(result.headers.get('cache-control')).toBe('no-store');
});
it.each([
  [{ elder_id: sessionId, language_preference: 'ZH_TW' }, ['tickets'], 400],
  [{ language_preference: 'NAN_TW' }, ['tickets'], 400],
  [{}, ['..', 'turns'], 404],
  [{}, [sessionId, 'asr-confirmation'], 404],
] as const)('rejects client scope and unsupported commands', async (body, path, status) => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  expect((await POST(request(body), { params: Promise.resolve({ path: [...path] }) })).status).toBe(status);
  expect(fetchMock).not.toHaveBeenCalled();
});
it('rejects foreign origins and staff credentials before contacting Core', async () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  const context = { params: Promise.resolve({ path: ['tickets'] }) };
  expect((await POST(request({}, 'https://foreign.invalid'), context)).status).toBe(403);
  expect((await POST(request({}, 'http://localhost:3000', 'kinsun_session=ks1_fake'), context)).status).toBe(401);
  expect(fetchMock).not.toHaveBeenCalled();
});
