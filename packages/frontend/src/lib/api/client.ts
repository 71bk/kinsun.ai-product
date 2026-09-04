export interface ApiConfig {
  apiBaseUrl: string;
}

interface ApiSuccessEnvelope {
  data: unknown;
  meta: {
    correlation_id: string;
    timestamp: string;
    schema_version: '1.0';
  };
}

interface ApiErrorEnvelope {
  error: {
    code:
      | 'bad_request'
      | 'authentication_required'
      | 'forbidden'
      | 'not_found'
      | 'conflict'
      | 'validation_error'
      | 'internal_error'
      | 'service_unavailable';
    message: string;
    correlation_id: string;
    reason_code: string | null;
    retryable: boolean;
    details: Array<{ field: string; reason: string }> | null;
  };
}

const ERROR_CODES = new Set<ApiErrorEnvelope['error']['code']>([
  'bad_request',
  'authentication_required',
  'forbidden',
  'not_found',
  'conflict',
  'validation_error',
  'internal_error',
  'service_unavailable',
]);

const PROTOCOL_ERROR_STATUS = 502;
const PROTOCOL_ERROR_REASON = 'MALFORMED_API_RESPONSE';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value);
  return actual.length === expected.length && expected.every((key) => actual.includes(key));
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

function isDateTime(value: unknown): value is string {
  return isNonEmptyString(value) && !Number.isNaN(Date.parse(value));
}

function isSuccessEnvelope(value: unknown): value is ApiSuccessEnvelope {
  if (!isRecord(value) || !hasExactKeys(value, ['data', 'meta']) || !isRecord(value.meta)) {
    return false;
  }

  return (
    hasExactKeys(value.meta, ['correlation_id', 'timestamp', 'schema_version']) &&
    isNonEmptyString(value.meta.correlation_id) &&
    isDateTime(value.meta.timestamp) &&
    value.meta.schema_version === '1.0'
  );
}

function isValidationDetail(value: unknown): value is { field: string; reason: string } {
  return (
    isRecord(value) &&
    hasExactKeys(value, ['field', 'reason']) &&
    typeof value.field === 'string' &&
    typeof value.reason === 'string'
  );
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!isRecord(value) || !hasExactKeys(value, ['error']) || !isRecord(value.error)) {
    return false;
  }

  const error = value.error;
  if (
    !hasExactKeys(error, [
      'code',
      'message',
      'correlation_id',
      'reason_code',
      'retryable',
      'details',
    ]) ||
    !isNonEmptyString(error.code) ||
    !ERROR_CODES.has(error.code as ApiErrorEnvelope['error']['code']) ||
    !isNonEmptyString(error.message) ||
    !isNonEmptyString(error.correlation_id) ||
    !(
      error.reason_code === null ||
      (isNonEmptyString(error.reason_code) && error.reason_code.length <= 120)
    ) ||
    typeof error.retryable !== 'boolean'
  ) {
    return false;
  }

  return error.details === null || (Array.isArray(error.details) && error.details.every(isValidationDetail));
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

function malformedResponseError(): ApiRequestError {
  return new ApiRequestError(
    PROTOCOL_ERROR_STATUS,
    'The server returned an invalid API response.',
    PROTOCOL_ERROR_REASON,
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

  if (response.ok && response.status === 204) return undefined as T;

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw malformedResponseError();
  }

  if (!response.ok) {
    if (!isErrorEnvelope(body)) throw malformedResponseError();
    throw new ApiRequestError(
      response.status,
      body.error.message,
      body.error.reason_code ?? undefined,
      body.error.retryable,
    );
  }

  if (!isSuccessEnvelope(body)) throw malformedResponseError();
  return body.data as T;
}

export function createIdempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
