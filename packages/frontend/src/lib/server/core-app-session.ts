import { normalizeAppSession } from './app-session-cookie';

const LOGOUT_PATH = '/api/v1/auth/logout';
const REQUEST_TIMEOUT_MS = 10_000;

function logoutTarget(): URL {
  const raw = process.env.CORE_API_INTERNAL_URL ?? 'http://127.0.0.1:8000';
  try {
    const base = new URL(raw);
    if (
      base.username ||
      base.password ||
      base.search ||
      base.hash ||
      (base.protocol !== 'http:' && base.protocol !== 'https:')
    ) {
      throw new Error('invalid');
    }
    const target = new URL(LOGOUT_PATH, base);
    if (target.origin !== base.origin || target.pathname !== LOGOUT_PATH)
      throw new Error('invalid');
    return target;
  } catch {
    throw new Error('Core App Session logout is unavailable');
  }
}

export async function revokeCoreAppSession(rawToken: unknown): Promise<void> {
  const token = normalizeAppSession(rawToken);
  if (!token) throw new Error('Core App Session logout is unavailable');
  let response: Response;
  try {
    response = await fetch(logoutTarget(), {
      method: 'POST',
      headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    throw new Error('Core App Session logout failed');
  }
  if (!response.ok) throw new Error('Core App Session logout failed');
}
