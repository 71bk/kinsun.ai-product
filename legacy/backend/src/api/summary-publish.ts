import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { SummaryRecord } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import { getAuthContext, HttpError, jsonResponse, requireAuthorization, requirePathParam, withErrorHandling } from './http.js';

/**
 * PUT /v1/elders/{elderId}/summaries/{date}/publish
 *
 * Extends B02 daily-summary generation with a family-visibility gate: a
 * summary is only readable by the `family` role once a caregiver explicitly
 * publishes it here (see listSummariesHandler's status==='published' filter
 * in summaries.ts). No existing requirement ID covers this — it's net-new
 * scope beyond the original spec, added for the family-facing report view.
 */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  const date = requirePathParam(event, 'date');
  requireAuthorization(authContext, 'summary', 'publish', elderId);

  const table = new DynamoTable();
  const existing = await table.getItem<SummaryRecord>(Keys.elderPk(elderId), Keys.summarySk(date));
  if (!existing) throw new HttpError(404, 'NOT_FOUND', `No summary for elder ${elderId} on ${date}`);

  const updated: SummaryRecord = {
    ...existing,
    status: 'published',
    publishedAt: new Date().toISOString(),
    publishedBy: authContext.userId,
  };
  await table.putItem(updated);

  return jsonResponse(200, updated);
});
