import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { AuthorizationContext, UserRole } from '@elderly-care/shared';
import { parseAuthorizerContext } from '../auth/authorizer.js';
import type { Action, Resource } from '../auth/permissions.js';
import { authorize } from '../auth/permissions.js';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Content-Type': 'application/json',
};

export function jsonResponse(statusCode: number, body: unknown): APIGatewayProxyResult {
  return { statusCode, headers: CORS_HEADERS, body: JSON.stringify(body) };
}

export class HttpError extends Error {
  constructor(
    public readonly statusCode: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export function getAuthContext(event: APIGatewayProxyEvent): AuthorizationContext {
  const raw = (event.requestContext as unknown as { authorizer?: Record<string, unknown> }).authorizer;
  if (!raw) throw new HttpError(401, 'UNAUTHORIZED', 'Missing authorizer context');
  return parseAuthorizerContext(raw) as AuthorizationContext & { role: UserRole };
}

export function requirePathParam(event: APIGatewayProxyEvent, name: string): string {
  const value = event.pathParameters?.[name];
  if (!value) throw new HttpError(400, 'BAD_REQUEST', `Missing path parameter: ${name}`);
  return value;
}

export function parseBody<T>(event: APIGatewayProxyEvent): T {
  if (!event.body) throw new HttpError(400, 'BAD_REQUEST', 'Missing request body');
  try {
    return JSON.parse(event.body) as T;
  } catch {
    throw new HttpError(400, 'BAD_REQUEST', 'Request body is not valid JSON');
  }
}

/** Enforces the role/resource/elder-scope check (H01.2, H01.3) before a handler touches any data. */
export function requireAuthorization(
  authContext: AuthorizationContext,
  resource: Resource,
  action: Action,
  elderId: string,
): void {
  if (!authorize(authContext, resource, action, elderId)) {
    throw new HttpError(403, 'FORBIDDEN', `${authContext.role} may not ${action} ${resource} for elder ${elderId}`);
  }
}

type Handler = (event: APIGatewayProxyEvent) => Promise<APIGatewayProxyResult>;

/** Wraps a handler so HttpError -> the right status code, and anything unexpected -> a logged 500. */
export function withErrorHandling(handler: Handler): Handler {
  return async (event) => {
    try {
      return await handler(event);
    } catch (err) {
      if (err instanceof HttpError) {
        return jsonResponse(err.statusCode, { code: err.code, message: err.message });
      }
      console.error('[api] unhandled error', err instanceof Error ? err.stack : err);
      return jsonResponse(500, { code: 'INTERNAL_ERROR', message: 'Unexpected server error' });
    }
  };
}
