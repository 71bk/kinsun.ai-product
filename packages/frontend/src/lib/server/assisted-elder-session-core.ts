const CORE_TIMEOUT_MS = 30_000;

function coreApiBaseUrl(): URL | null {
  try {
    const url = new URL(process.env.CORE_API_INTERNAL_URL ?? 'http://127.0.0.1:8000');
    if (url.username || url.password || (url.protocol !== 'http:' && url.protocol !== 'https:')) {
      return null;
    }
    url.pathname = `${url.pathname.replace(/\/+$/, '')}/`;
    url.search = '';
    url.hash = '';
    return url;
  } catch {
    return null;
  }
}
export async function assistedElderCoreRequest(
  path: string,
  init: RequestInit,
  elderSession?: string,
): Promise<Response> {
  const base = coreApiBaseUrl();
  if (!base || path.startsWith('/') || path.includes('..')) {
    throw new Error('INVALID_CORE_TARGET');
  }
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body !== undefined) headers.set('Content-Type', 'application/json');
  if (elderSession) headers.set('Authorization', `Bearer ${elderSession}`);
  return fetch(new URL(path, base), {
    ...init,
    headers,
    cache: 'no-store',
    redirect: 'manual',
    signal: AbortSignal.timeout(CORE_TIMEOUT_MS),
  });
}

export function noStoreCoreResponse(upstream: Response): Response {
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'Cache-Control': 'no-store',
      'Content-Type': upstream.headers.get('content-type') ?? 'application/json',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}
