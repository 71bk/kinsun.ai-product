import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { EventRecord, EventSummary, ListEventsResponse, ReviewChange, UpdateEventRequest } from '@elderly-care/shared';
import { DynamoTable, GSI2, Keys } from '../db/index.js';
import { getAuthContext, jsonResponse, requireAuthorization, requirePathParam, parseBody, withErrorHandling } from './http.js';

function toSummary(record: EventRecord): EventSummary {
  return {
    eventId: record.eventId,
    eventType: record.eventType,
    content: record.content,
    eventDate: record.eventDate,
    confidence: record.confidence,
    reviewStatus: record.reviewStatus,
    sourceConversationId: record.sourceConversationId,
    correctionCount: record.reviewHistory.length,
  };
}

/**
 * GET /v1/elders/{elderId}/events (B04.1-B04.4). Queries the elder's full
 * EVENT# partition and filters in-memory — GSI1/GSI2 exist for
 * type/review-status lookups at larger scale, but a single elder's event
 * volume in this system is small enough that a partition scan + filter is
 * simpler and still fast.
 */
export const listEventsHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  requireAuthorization(authContext, 'event', 'read', elderId);

  const { dateFrom, dateTo, eventType, reviewStatus } = event.queryStringParameters ?? {};

  const table = new DynamoTable();
  const records = await table.queryByPk<EventRecord>(Keys.elderPk(elderId), Keys.eventSkPrefix());

  const filtered = records.filter((r) => {
    if (dateFrom && r.eventDate < dateFrom) return false;
    if (dateTo && r.eventDate > dateTo) return false;
    if (eventType && r.eventType !== eventType) return false;
    if (reviewStatus && r.reviewStatus !== reviewStatus) return false;
    return true;
  });

  const response: ListEventsResponse = { items: filtered.map(toSummary), nextCursor: null };
  return jsonResponse(200, response);
});

/** PUT /v1/events/{eventId} — caregiver correction, recorded in reviewHistory (B03.1, B03.2). */
export const updateEventHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const eventId = requirePathParam(event, 'eventId');
  const body = parseBody<UpdateEventRequest>(event);
  requireAuthorization(authContext, 'event', 'write', body.elderId);

  const table = new DynamoTable();
  const pk = Keys.elderPk(body.elderId);
  const sk = Keys.eventSk(body.eventDate, eventId);
  const existing = await table.getItem<EventRecord>(pk, sk);
  if (!existing) return jsonResponse(404, { code: 'NOT_FOUND', message: 'Event not found' });

  const now = new Date().toISOString();
  const changes: ReviewChange[] = [];
  const updated: EventRecord = { ...existing };

  if (body.content !== undefined && body.content !== existing.content) {
    changes.push({ previousValue: existing.content, newValue: body.content, changedBy: body.updatedBy, changedAt: now, field: 'content' });
    updated.content = body.content;
  }
  if (body.eventType !== undefined && body.eventType !== existing.eventType) {
    changes.push({ previousValue: existing.eventType, newValue: body.eventType, changedBy: body.updatedBy, changedAt: now, field: 'eventType' });
    updated.eventType = body.eventType;
    updated.GSI1PK = `${pk}#EVENT_TYPE#${body.eventType}`;
  }
  if (body.reviewStatus !== undefined && body.reviewStatus !== existing.reviewStatus) {
    changes.push({ previousValue: existing.reviewStatus, newValue: body.reviewStatus, changedBy: body.updatedBy, changedAt: now, field: 'reviewStatus' });
    updated.reviewStatus = body.reviewStatus;
    updated.GSI2PK = GSI2.pk(body.elderId, body.reviewStatus);
  }

  updated.reviewHistory = [...existing.reviewHistory, ...changes]; // append-only, same invariant as Memory's auditTrail (Property 9)
  updated.updatedAt = now;

  await table.putItem(updated);
  return jsonResponse(200, toSummary(updated));
});
