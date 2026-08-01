import {
  ApiGatewayManagementApiClient,
  PostToConnectionCommand,
} from '@aws-sdk/client-apigatewaymanagementapi';
import type { APIGatewayEventRequestContextV2WithAuthorizer } from 'aws-lambda';

/** Posts a JSON message back to a connected voice client over the WebSocket. */
export async function postToConnection(
  requestContext: Pick<APIGatewayEventRequestContextV2WithAuthorizer<unknown>, 'domainName' | 'stage'> & {
    connectionId: string;
  },
  payload: unknown,
): Promise<void> {
  const client = new ApiGatewayManagementApiClient({
    endpoint: `https://${requestContext.domainName}/${requestContext.stage}`,
  });
  await client.send(
    new PostToConnectionCommand({
      ConnectionId: requestContext.connectionId,
      Data: Buffer.from(JSON.stringify(payload)),
    }),
  );
}
