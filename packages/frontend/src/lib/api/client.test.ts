import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError, apiFetch, type ApiConfig } from './client';

const config: ApiConfig = { apiBaseUrl: '/backend/core/' };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function validMeta(): Record<string, unknown> {
  return {
    correlation_id: '8dfb1042-2de8-4b65-9373-fd56a282b327',
    timestamp: '2026-09-04T00:00:00Z',
    schema_version: '1.0',
  };
}

async function caughtRequest(): Promise<ApiRequestError> {
  const caught = await apiFetch(config, '/api/v1/example').catch((error: unknown) => error);
  expect(caught).toBeInstanceOf(ApiRequestError);
  return caught as ApiRequestError;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('apiFetch response validation', () => {
  it('returns data from a contract-valid success envelope', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ data: { value: 7 }, meta: validMeta() })));

    await expect(apiFetch<{ value: number }>(config, '/api/v1/example')).resolves.toEqual({
      value: 7,
    });
  });

  it.each([
    ['missing data', { meta: validMeta() }],
    ['missing meta', { data: { value: 7 } }],
    ['wrong correlation id type', { data: {}, meta: { ...validMeta(), correlation_id: 42 } }],
    ['invalid timestamp', { data: {}, meta: { ...validMeta(), timestamp: 'not-a-date' } }],
    ['unknown schema version', { data: {}, meta: { ...validMeta(), schema_version: '2.0' } }],
    ['extra envelope field', { data: {}, meta: validMeta(), legacy: true }],
    ['extra metadata field', { data: {}, meta: { ...validMeta(), request_id: 'legacy' } }],
  ])('rejects a malformed success envelope: %s', async (_label, body) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(body)));

    await expect(caughtRequest()).resolves.toMatchObject({
      status: 502,
      reasonCode: 'MALFORMED_API_RESPONSE',
      retryable: false,
    });
  });

  it('preserves fields from a contract-valid error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          {
            error: {
              code: 'service_unavailable',
              message: 'Service is temporarily unavailable.',
              correlation_id: '8dfb1042-2de8-4b65-9373-fd56a282b327',
              reason_code: 'SERVICE_UNAVAILABLE',
              retryable: true,
              details: null,
            },
          },
          503,
        ),
      ),
    );

    await expect(caughtRequest()).resolves.toMatchObject({
      status: 503,
      message: 'Service is temporarily unavailable.',
      reasonCode: 'SERVICE_UNAVAILABLE',
      retryable: true,
    });
  });

  it.each([
    [
      'missing required field',
      {
        error: {
          code: 'forbidden',
          message: 'Forbidden.',
          correlation_id: '8dfb1042-2de8-4b65-9373-fd56a282b327',
          reason_code: null,
          retryable: false,
        },
      },
    ],
    [
      'wrong retryable type',
      {
        error: {
          code: 'service_unavailable',
          message: 'Unavailable.',
          correlation_id: '8dfb1042-2de8-4b65-9373-fd56a282b327',
          reason_code: null,
          retryable: 'yes',
          details: null,
        },
      },
    ],
    [
      'unknown error code',
      {
        error: {
          code: 'legacy_error',
          message: 'Legacy error.',
          correlation_id: '8dfb1042-2de8-4b65-9373-fd56a282b327',
          reason_code: null,
          retryable: false,
          details: null,
        },
      },
    ],
  ])('rejects a malformed error envelope: %s', async (_label, body) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(body, 403)));

    const error = await caughtRequest();
    expect(error).toMatchObject({
      status: 502,
      reasonCode: 'MALFORMED_API_RESPONSE',
      retryable: false,
    });
    expect(error.message).not.toContain(JSON.stringify(body));
  });

  it('normalizes invalid JSON without exposing the response body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response('<html>upstream proxy error</html>', {
            status: 502,
            headers: { 'Content-Type': 'text/html' },
          }),
      ),
    );

    const error = await caughtRequest();
    expect(error).toMatchObject({
      status: 502,
      reasonCode: 'MALFORMED_API_RESPONSE',
    });
    expect(error.message).not.toContain('upstream proxy error');
  });

  it('accepts a successful 204 response without parsing a body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })));

    await expect(apiFetch<void>(config, '/api/v1/example', { method: 'DELETE' })).resolves.toBeUndefined();
  });
});
