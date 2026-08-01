import { ulid } from 'ulid';
import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { ConversationRecord, StartConversationRequest, StartConversationResponse } from '@elderly-care/shared';
import { computeTtlEpochSeconds, DynamoTable, Keys, RETENTION_DAYS } from '../db/index.js';
import { generateTraceId } from '../workflow/trace.js';
import { getAuthContext, jsonResponse, parseBody, requireAuthorization, withErrorHandling } from './http.js';

/** POST /v1/conversations/start (B04.1 prerequisite — every event/summary traces back to a conversationId). */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const { elderId } = parseBody<StartConversationRequest>(event);
  requireAuthorization(authContext, 'conversation', 'read', elderId);

  const conversationId = `conv_${ulid()}`;
  const traceId = generateTraceId();
  const now = new Date().toISOString();

  const record: ConversationRecord = {
    PK: Keys.elderPk(elderId),
    SK: Keys.conversationSk(now, conversationId),
    conversationId,
    elderId,
    startTime: now,
    endTime: null,
    turns: [],
    asrMetadata: null,
    status: 'active',
    traceId,
    audioS3Key: null,
    ttl: computeTtlEpochSeconds(RETENTION_DAYS.conversation),
  };

  await new DynamoTable().putItem(record);

  const response: StartConversationResponse = {
    conversationId,
    traceId,
    websocketUrl: process.env.WEBSOCKET_URL ?? '',
  };
  return jsonResponse(201, response);
});
