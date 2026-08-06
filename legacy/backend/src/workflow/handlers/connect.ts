import type { APIGatewayProxyResultV2, APIGatewayProxyWebsocketEventV2 } from 'aws-lambda';
import { buildAuthorizationContext } from '../../auth/context.js';
import { verifyIdToken } from '../../auth/jwt.js';
import { ConnectionStore } from '../connection-store.js';

/**
 * WebSocket $connect route. The voice client passes its Cognito ID token as
 * a query-string parameter (WebSocket handshakes cannot carry custom
 * headers from a browser), which we verify the same way the REST
 * authorizer does before persisting the connection's elder_id.
 */
export async function handler(
  event: APIGatewayProxyWebsocketEventV2,
): Promise<APIGatewayProxyResultV2> {
  const token = event.queryStringParameters?.token;
  if (!token) {
    return { statusCode: 401, body: 'Missing token' };
  }

  try {
    const identity = await verifyIdToken(token);
    const authContext = await buildAuthorizationContext(identity.userId, identity.role, identity.tenantId);

    if (identity.role !== 'elder') {
      return { statusCode: 403, body: 'Only elder identities may open a voice session' };
    }

    await new ConnectionStore().save(
      event.requestContext.connectionId,
      authContext.authorizedElderIds[0] ?? identity.userId,
      identity.role,
    );
    return { statusCode: 200, body: 'Connected' };
  } catch {
    return { statusCode: 401, body: 'Unauthorized' };
  }
}
