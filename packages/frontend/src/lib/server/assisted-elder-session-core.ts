import { resolveCoreApiBaseUrl } from './core-api-url';

const CORE_TIMEOUT_MS = 30_000;
export async function assistedElderCoreRequest(
  path: string,
  init: RequestInit,
  elderSession?: string,
): Promise<Response> {
  const base = resolveCoreApiBaseUrl({ allowLocalDefault: true });
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
