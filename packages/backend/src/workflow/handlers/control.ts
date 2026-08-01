import { ulid } from 'ulid';
import type { APIGatewayProxyResultV2, APIGatewayProxyWebsocketEventV2 } from 'aws-lambda';
import { ConnectionStore } from '../connection-store.js';
import { generateTraceId } from '../trace.js';
import { postToConnection } from './ws-reply.js';

interface ControlMessage {
  /** Route-selection field API Gateway consumes ($request.body.action) — always "control" on this route. */
  action: 'control';
  /** The actual session-level signal this message carries. */
  type: 'start' | 'stop' | 'cancel';
}

/**
 * WebSocket `control` route — carries session-level signals (start/stop/
 * cancel) separate from the `audio` route's binary payload. `start`
 * allocates the conversationId + traceId that every subsequent `audio`
 * message and workflow-stage log for this session will share (J04.2).
 *
 * Note: the top-level `action` field is API Gateway's route-selection key
 * (routeSelectionExpression: $request.body.action) — it's how this handler
 * gets invoked at all, so the actual command is carried in a separate
 * `type` field to avoid colliding with it.
 */
export async function handler(
  event: APIGatewayProxyWebsocketEventV2,
): Promise<APIGatewayProxyResultV2> {
  const connectionId = event.requestContext.connectionId;
  const store = new ConnectionStore();
  const connection = await store.get(connectionId);
  if (!connection) {
    return { statusCode: 401, body: 'Unknown connection' };
  }

  const message = JSON.parse(event.body ?? '{}') as ControlMessage;

  if (message.type === 'start') {
    const conversationId = `conv_${ulid()}`;
    const traceId = generateTraceId();
    await store.attachConversation(connectionId, conversationId, traceId);
    await postToConnection(event.requestContext, { type: 'state', state: 'recording', conversationId, traceId });
  } else if (message.type === 'stop' || message.type === 'cancel') {
    await postToConnection(event.requestContext, { type: 'state', state: 'idle' });
  }

  return { statusCode: 200, body: 'OK' };
}
