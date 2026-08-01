import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { ConversationRecord, EventRecord, EventType, ReportResponse } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import { getAuthContext, jsonResponse, requireAuthorization, requirePathParam, withErrorHandling } from './http.js';

const EVENT_TYPES: EventType[] = ['meal', 'activity', 'sleep', 'medication_statement', 'emotion', 'important_event'];

function rangeStart(range: 'week' | 'year', now: Date): Date {
  const start = new Date(now);
  if (range === 'week') start.setDate(start.getDate() - 7);
  else start.setFullYear(start.getFullYear() - 1);
  return start;
}

/**
 * GET /v1/elders/{elderId}/reports?range=week|year (A07.1-A07.4). Only
 * counts events that passed schema validation and are already persisted
 * (A07.4) — there's no code path here that fabricates or infers a data
 * point beyond what's in DynamoDB.
 */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  requireAuthorization(authContext, 'event', 'read', elderId);

  const range = (event.queryStringParameters?.range === 'year' ? 'year' : 'week') as 'week' | 'year';
  const now = new Date();
  const dateFrom = rangeStart(range, now).toISOString().slice(0, 10);
  const dateTo = now.toISOString().slice(0, 10);

  const table = new DynamoTable();
  const [events, conversations] = await Promise.all([
    table.queryByPk<EventRecord>(Keys.elderPk(elderId), Keys.eventSkPrefix()),
    table.queryByPk<ConversationRecord>(Keys.elderPk(elderId), Keys.conversationSkPrefix()),
  ]);

  const inRange = events.filter((e) => e.eventDate >= dateFrom && e.eventDate <= dateTo);
  const eventCountByType = Object.fromEntries(
    EVENT_TYPES.map((t) => [t, inRange.filter((e) => e.eventType === t).length]),
  ) as Record<EventType, number>;

  const totalInteractions = conversations.filter((c) => c.startTime.slice(0, 10) >= dateFrom).length;

  const rangeLabel = range === 'week' ? '這一週' : '這一年';
  const voiceSummary = `${rangeLabel}您總共互動了 ${totalInteractions} 次，飲食紀錄 ${eventCountByType.meal} 筆，活動紀錄 ${eventCountByType.activity} 筆，睡眠紀錄 ${eventCountByType.sleep} 筆。`;

  const response: ReportResponse = { range, dateFrom, dateTo, eventCountByType, totalInteractions, voiceSummary };
  return jsonResponse(200, response);
});
