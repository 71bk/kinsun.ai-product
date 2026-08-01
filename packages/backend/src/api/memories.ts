import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type {
  CandidateMemory,
  ConfirmMemoryRequest,
  ConfirmedMemory,
  ListMemoriesResponse,
  MemoryRecord,
  RejectMemoryRequest,
} from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import { MemoryManager } from '../memory/manager.js';
import { getAuthContext, jsonResponse, parseBody, requireAuthorization, requirePathParam, withErrorHandling } from './http.js';

function toCandidate(r: MemoryRecord): CandidateMemory {
  return {
    memoryId: r.memoryId,
    elderId: r.elderId,
    category: r.category,
    content: r.content,
    sourceConversationId: r.sourceConversationId,
    confidence: r.confidence,
    createdAt: r.createdAt,
    status: r.status === 'confirmed' || r.status === 'rejected' ? r.status : 'pending',
  };
}

function toConfirmed(r: MemoryRecord): ConfirmedMemory {
  return {
    memoryId: r.memoryId,
    elderId: r.elderId,
    category: r.category,
    content: r.content,
    confirmedBy: r.confirmedBy ?? '',
    confirmedAt: r.confirmedAt ?? '',
    sourceConversationId: r.sourceConversationId,
    isActive: r.isActive,
    lastUsedAt: r.lastUsedAt,
  };
}

/** GET /v1/elders/{elderId}/memories (D02.3, D04.1). */
export const listMemoriesHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  requireAuthorization(authContext, 'memory', 'read', elderId);

  const table = new DynamoTable();
  const [candidateRecords, confirmedRecords] = await Promise.all([
    table.queryByPk<MemoryRecord>(Keys.elderPk(elderId), Keys.memorySkPrefix('candidate')),
    table.queryByPk<MemoryRecord>(Keys.elderPk(elderId), Keys.memorySkPrefix('confirmed')),
  ]);

  const response: ListMemoriesResponse = {
    candidates: candidateRecords.filter((r) => r.status === 'pending').map(toCandidate),
    confirmed: confirmedRecords.filter((r) => r.status === 'confirmed' && r.isActive).map(toConfirmed),
  };
  return jsonResponse(200, response);
});

/** PUT /v1/memories/{memoryId}/confirm (D02.3). */
export const confirmMemoryHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const memoryId = requirePathParam(event, 'memoryId');
  const body = parseBody<ConfirmMemoryRequest>(event);
  requireAuthorization(authContext, 'memory', 'confirm', body.elderId);

  const confirmed = await new MemoryManager().confirm(body.elderId, memoryId, body.confirmerId);
  return jsonResponse(200, confirmed);
});

/** PUT /v1/memories/{memoryId}/reject (D02.2) — not in design.md's endpoint table but required by the reject() flow. */
export const rejectMemoryHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const memoryId = requirePathParam(event, 'memoryId');
  const body = parseBody<RejectMemoryRequest>(event);
  requireAuthorization(authContext, 'memory', 'confirm', body.elderId);

  await new MemoryManager().reject(body.elderId, memoryId, body.rejecterId);
  return jsonResponse(204, null);
});

/** DELETE /v1/memories/{memoryId}?elderId=... (D04.1). elderId travels as a query param — DELETE bodies aren't reliably proxied everywhere. */
export const deleteMemoryHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const memoryId = requirePathParam(event, 'memoryId');
  const elderId = event.queryStringParameters?.elderId;
  if (!elderId) return jsonResponse(400, { code: 'BAD_REQUEST', message: 'Missing elderId query parameter' });
  requireAuthorization(authContext, 'memory', 'delete', elderId);

  await new MemoryManager().delete(elderId, memoryId);
  return jsonResponse(204, null);
});
