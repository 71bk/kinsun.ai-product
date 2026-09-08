import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { bffError } from '../server/bff-response';
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

function coreError(overrides: Record<string, unknown> = {}) {
  return { error: {
    code: 'not_found', message: 'Resource not found', correlation_id: 'synthetic-correlation',
    reason_code: null, retryable: false, details: null, ...overrides,
  } };
}

describe('current Core and BFF protocol compatibility', () => {
  const coreSchema = JSON.parse(readFileSync(
    new URL('../../../../../contracts/schemas/common/ErrorEnvelopeV1.json', import.meta.url), 'utf8',
  ));

  it.each(coreSchema.$defs.ErrorBody.properties.code.enum as string[])(
    'accepts the current Core error code %s', async (code) => {
      vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(coreError({ code }), 422)));
      await expect(caughtRequest()).resolves.toMatchObject({ status: 422, message: 'Resource not found' });
    },
  );

  it.each([
    [400, 'bad_request', 'INVALID_PROXY_REQUEST', false],
    [401, 'unauthorized', 'AUTHENTICATION_REQUIRED', false],
    [403, 'forbidden', 'CSRF_ORIGIN_REJECTED', false],
    [413, 'payload_too_large', 'PAYLOAD_TOO_LARGE', false],
    [502, 'bad_gateway', 'CORE_API_UNAVAILABLE', true],
    [504, 'gateway_timeout', 'CORE_API_TIMEOUT', true],
  ] as const)('accepts the real BFF producer for HTTP %s', async (status, code, reason, retryable) => {
    vi.stubGlobal('fetch', vi.fn(async () => bffError(status, code, 'Synthetic BFF failure', reason, retryable)));
    await expect(caughtRequest()).resolves.toMatchObject({
      status, message: 'Synthetic BFF failure', reasonCode: reason, retryable,
    });
  });

  it.each([401, 403, 404, 409, 422, 500])(
    'preserves HTTP %s when denial/error content is malformed', async (status) => {
      const fetchMock = vi.fn(async () => new Response('<html>synthetic private value</html>', { status }));
      vi.stubGlobal('fetch', fetchMock);
      const error = await caughtRequest();
      expect(error).toMatchObject({ status, reasonCode: 'MALFORMED_API_RESPONSE', retryable: false });
      expect(error.message).not.toContain('synthetic private value');
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it.each([401, 403, 404])('never returns success-shaped data from HTTP %s', async (status) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ data: { private: true }, meta: validMeta() }, status)));
    await expect(caughtRequest()).resolves.toMatchObject({ status, reasonCode: 'MALFORMED_API_RESPONSE' });
  });

  it.each([
    { code: 'unknown_code' }, { message: '' }, { correlation_id: '' }, { reason_code: '' },
    { reason_code: 'x'.repeat(121) }, { retryable: null }, { details: {} },
    { details: [null] }, { details: [{ field: 1, reason: 'invalid' }] },
    { details: [{ field: 'title', reason: 'invalid', private: 'synthetic' }] },
    { extra: true },
  ])('rejects invalid Core error fields %#', async (overrides) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(coreError(overrides), 422)));
    await expect(caughtRequest()).resolves.toMatchObject({ status: 422, reasonCode: 'MALFORMED_API_RESPONSE' });
  });

  it.each(coreSchema.$defs.ErrorBody.required as string[])(
    'rejects a missing Core error field %s', async (field) => {
      const body: { error: Record<string, unknown> } = coreError();
      delete body.error[field];
      vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(body, 404)));
      await expect(caughtRequest()).resolves.toMatchObject({ status: 404, reasonCode: 'MALFORMED_API_RESPONSE' });
    },
  );

  it('accepts contract-valid validation details and nullable reasons', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(coreError({
      code: 'validation_error', details: [{ field: 'title', reason: 'Required' }],
    }), 422)));
    await expect(caughtRequest()).resolves.toMatchObject({ status: 422, reasonCode: undefined, retryable: false });
  });

  it.each([
    null, [], 'unexpected', 42, {}, { data: {}, meta: null },
    { data: {}, meta: validMeta(), error: coreError().error }, coreError(),
  ])('rejects invalid success body %#', async (body) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(body)));
    await expect(caughtRequest()).resolves.toMatchObject({ status: 502, reasonCode: 'MALFORMED_API_RESPONSE' });
  });

  it.each([
    '2026-09-08', 'September 8, 2026', '2026-09-08T12:00:00',
    '2026-02-29T00:00:00Z', '2026-02-30T00:00:00Z', '2026-13-01T00:00:00Z',
    '2026-09-08T24:00:00Z', '2026-09-08T12:00:00+99:00',
  ])('rejects invalid metadata timestamp %s', async (timestamp) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ data: {}, meta: { ...validMeta(), timestamp } })));
    await expect(caughtRequest()).resolves.toMatchObject({ reasonCode: 'MALFORMED_API_RESPONSE' });
  });

  it.each(['2024-02-29T00:00:00Z', '2026-09-08T12:00:00.123456+00:00', '2026-09-08T20:00:00+08:00'])(
    'accepts timezone-aware metadata timestamp %s', async (timestamp) => {
      vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ data: {}, meta: { ...validMeta(), timestamp } })));
      await expect(apiFetch(config, '/api/v1/example')).resolves.toEqual({});
    },
  );

  it('does not pretend to validate the domain DTO inside data', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ data: null, meta: validMeta() })));
    await expect(apiFetch<unknown>(config, '/api/v1/example')).resolves.toBeNull();
  });

  it.each(['missing-meta', 'wrong-version', 'extra-field', 'hybrid-core', 'unknown-code', 'wrong-type'])(
    'rejects malformed BFF errors: %s', async (variant) => {
      const body = await bffError(401, 'unauthorized', 'Synthetic failure', 'AUTHENTICATION_REQUIRED').json();
      if (variant === 'missing-meta') delete body.meta;
      if (variant === 'wrong-version') body.meta.schema_version = '2.0';
      if (variant === 'extra-field') body.extra = true;
      if (variant === 'hybrid-core') body.error.correlation_id = 'synthetic';
      if (variant === 'unknown-code') body.error.code = 'unknown';
      if (variant === 'wrong-type') body.error.retryable = 'true';
      vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(body, 401)));
      await expect(caughtRequest()).resolves.toMatchObject({ status: 401, reasonCode: 'MALFORMED_API_RESPONSE' });
    },
  );

  it('leaves a network failure untouched and never retries the request', async () => {
    const failure = new TypeError('Synthetic network failure');
    const fetchMock = vi.fn().mockRejectedValue(failure);
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiFetch(config, '/api/v1/example')).rejects.toBe(failure);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
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
      status: 403,
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
