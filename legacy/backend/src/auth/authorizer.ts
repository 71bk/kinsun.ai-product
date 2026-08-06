import type {
  APIGatewayAuthorizerResult,
  APIGatewayRequestAuthorizerEvent,
  PolicyDocument,
} from 'aws-lambda';
import { DynamoTable } from '../db/index.js';
import { buildAuthorizationContext } from './context.js';
import { verifyIdToken } from './jwt.js';

function policy(effect: 'Allow' | 'Deny', resource: string): PolicyDocument {
  return {
    Version: '2012-10-17',
    Statement: [{ Action: 'execute-api:Invoke', Effect: effect, Resource: resource }],
  };
}

/**
 * API Gateway REQUEST Lambda Authorizer (H01). On success, the resolved
 * AuthorizationContext is serialized into the authorizer `context` object —
 * API Gateway only allows string values there, so authorizedElderIds is
 * joined with commas and re-split by downstream handlers.
 */
export async function handler(
  event: APIGatewayRequestAuthorizerEvent,
): Promise<APIGatewayAuthorizerResult> {
  const authHeader = event.headers?.['Authorization'] ?? event.headers?.['authorization'];
  const token = authHeader?.replace(/^Bearer\s+/i, '');

  if (!token) {
    throw new Error('Unauthorized');
  }

  try {
    const identity = await verifyIdToken(token);
    const authContext = await buildAuthorizationContext(
      identity.userId,
      identity.role,
      identity.tenantId,
      new DynamoTable(),
    );

    return {
      principalId: identity.userId,
      policyDocument: policy('Allow', event.methodArn),
      context: {
        userId: authContext.userId,
        role: authContext.role,
        tenantId: authContext.tenantId,
        authorizedElderIds: authContext.authorizedElderIds.join(','),
      },
    };
  } catch {
    // Any verification failure is an unauthenticated request, not a 5xx —
    // API Gateway maps a thrown "Unauthorized" to 401 automatically.
    throw new Error('Unauthorized');
  }
}

/** Reconstructs AuthorizationContext from the string-only authorizer context on downstream events. */
export function parseAuthorizerContext(context: Record<string, unknown>) {
  const authorizedElderIds = String(context.authorizedElderIds ?? '')
    .split(',')
    .filter(Boolean);
  return {
    userId: String(context.userId ?? ''),
    role: context.role as 'elder' | 'caregiver' | 'family' | 'admin',
    tenantId: String(context.tenantId ?? ''),
    authorizedElderIds,
  };
}
