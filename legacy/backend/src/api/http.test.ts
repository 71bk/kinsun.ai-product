import { describe, expect, it } from 'vitest';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { getAuthContext, HttpError, parseBody, requireAuthorization, requirePathParam } from './http.js';

function fakeEvent(overrides: Partial<APIGatewayProxyEvent> = {}): APIGatewayProxyEvent {
  return {
    body: null,
    headers: {},
    pathParameters: null,
    queryStringParameters: null,
    requestContext: {} as never,
    ...overrides,
  } as APIGatewayProxyEvent;
}

describe('getAuthContext', () => {
  it('parses the authorizer context set by the Lambda Authorizer', () => {
    const event = fakeEvent({
      requestContext: {
        authorizer: { userId: 'u1', role: 'caregiver', tenantId: 't1', authorizedElderIds: 'e1,e2' },
      } as never,
    });
    const ctx = getAuthContext(event);
    expect(ctx.userId).toBe('u1');
    expect(ctx.role).toBe('caregiver');
    expect(ctx.authorizedElderIds).toEqual(['e1', 'e2']);
  });

  it('throws 401 when the authorizer context is missing', () => {
    expect(() => getAuthContext(fakeEvent())).toThrow(HttpError);
  });
});

describe('requirePathParam / parseBody', () => {
  it('throws 400 when a required path param is missing', () => {
    expect(() => requirePathParam(fakeEvent(), 'elderId')).toThrow(HttpError);
  });

  it('returns the path param when present', () => {
    expect(requirePathParam(fakeEvent({ pathParameters: { elderId: 'e1' } }), 'elderId')).toBe('e1');
  });

  it('throws 400 for missing or malformed JSON body', () => {
    expect(() => parseBody(fakeEvent())).toThrow(HttpError);
    expect(() => parseBody(fakeEvent({ body: '{not json' }))).toThrow(HttpError);
  });

  it('parses a valid JSON body', () => {
    expect(parseBody<{ x: number }>(fakeEvent({ body: '{"x":1}' }))).toEqual({ x: 1 });
  });
});

describe('requireAuthorization', () => {
  it('throws 403 when the caregiver is not authorized for the requested elder', () => {
    expect(() =>
      requireAuthorization({ userId: 'cg1', role: 'caregiver', authorizedElderIds: ['e1'], tenantId: 't1' }, 'event', 'write', 'e2'),
    ).toThrow(HttpError);
  });

  it('passes silently when authorized', () => {
    expect(() =>
      requireAuthorization({ userId: 'cg1', role: 'caregiver', authorizedElderIds: ['e1'], tenantId: 't1' }, 'event', 'write', 'e1'),
    ).not.toThrow();
  });
});
