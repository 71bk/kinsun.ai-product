import type { APIGatewayProxyResultV2, APIGatewayProxyWebsocketEventV2 } from 'aws-lambda';
import { ConnectionStore } from '../connection-store.js';

export async function handler(
  event: APIGatewayProxyWebsocketEventV2,
): Promise<APIGatewayProxyResultV2> {
  await new ConnectionStore().remove(event.requestContext.connectionId);
  return { statusCode: 200, body: 'Disconnected' };
}
