import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { SummaryRecord } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import { getAuthContext, HttpError, jsonResponse, requireAuthorization, requirePathParam, withErrorHandling } from './http.js';

/**
 * PUT /v1/elders/{elderId}/summaries/{date}/withdraw
 *
 * Reverses summary-publish.ts: the family role immediately stops seeing this
 * summary again. publishedAt/publishedBy are intentionally left untouched
 * (not nulled out) so who last published, and when, survives a withdraw.
 */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  const date = requirePathParam(event, 'date');
  requireAuthorization(authContext, 'summary', 'publish', elderId);

  const table = new DynamoTable();
  const existing = await table.getItem<SummaryRecord>(Keys.elderPk(elderId), Keys.summarySk(date));
  if (!existing) throw new HttpError(404, 'NOT_FOUND', `No summary for elder ${elderId} on ${date}`);

  const updated: SummaryRecord = { ...existing, status: 'withdrawn' };
  await table.putItem(updated);

  return jsonResponse(200, updated);
});
