import { isErrorEnvelope, isSuccessEnvelope } from './response-envelope';

export interface ApiConfig {
  apiBaseUrl: string;
}

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly reasonCode?: string,
    public readonly retryable: boolean = false,
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

function malformedResponseError(response: Response): ApiRequestError {
  // Preserve HTTP denials even if a proxy returned HTML or a broken envelope.
  // Turning a 401/403/404 into 502 would bypass the UI's access-loss recovery.
  return new ApiRequestError(
    response.ok ? 502 : response.status,
    'The server returned an invalid API response.',
    'MALFORMED_API_RESPONSE',
    false,
  );
}

/**
 * Thin same-origin fetch wrapper shared by every REST client module. Browser
 * JavaScript never reads or attaches credentials: the HttpOnly cookie goes to
 * the Next.js BFF, which adds Core's Bearer header server-side.
 */
export async function apiFetch<T>(
  config: ApiConfig,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const base = config.apiBaseUrl.replace(/\/+$/, '');
  const headers = new Headers(init.headers);
  headers.delete('Authorization');
  if (init.body !== undefined) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  });

  if (response.status === 204) return undefined as T;

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw malformedResponseError(response);
  }

  if (!response.ok) {
    if (!isErrorEnvelope(body)) throw malformedResponseError(response);
    throw new ApiRequestError(
      response.status,
      body.error.message,
      body.error.reason_code ?? undefined,
      body.error.retryable,
    );
  }

  if (!isSuccessEnvelope(body)) throw malformedResponseError(response);
  return body.data as T;
}

export function createIdempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
