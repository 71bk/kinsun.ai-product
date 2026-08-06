import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { SummaryRecord } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import { getAuthContext, jsonResponse, requireAuthorization, requirePathParam, withErrorHandling } from './http.js';

/**
 * Per 04｜資訊架構、UX 與 User Flow §7.3, a withdrawn report must still show as
 * "已撤回" to family (so a previously-seen item doesn't just silently vanish)
 * but must never retain its old narrative content. Everything except the
 * identity/lifecycle fields is zeroed out before this ever leaves the API.
 */
function redactWithdrawn(record: SummaryRecord): SummaryRecord {
  return {
    ...record,
    content: {
      overview: '',
      meals: [],
      activities: [],
      sleep: null,
      medicationStatements: [],
      importantEvents: [],
      emotionalState: null,
    },
    sourceEventIds: [],
  };
}

/** GET /v1/elders/{elderId}/summaries (B02.3, C02.1). */
export const listSummariesHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  requireAuthorization(authContext, 'summary', 'read', elderId);

  const { dateFrom, dateTo } = event.queryStringParameters ?? {};
  const records = await new DynamoTable().queryByPk<SummaryRecord>(Keys.elderPk(elderId), Keys.summarySkPrefix());
  let filtered = records.filter((r) => (!dateFrom || r.date >= dateFrom) && (!dateTo || r.date <= dateTo));

  // Family never sees a draft at all (it doesn't exist to them yet), but a
  // withdrawn report stays visible as a redacted placeholder — see
  // redactWithdrawn. Unlike dateFrom/dateTo, this is not client-controllable.
  if (authContext.role === 'family') {
    filtered = filtered
      .filter((r) => r.status === 'published' || r.status === 'withdrawn')
      .map((r) => (r.status === 'withdrawn' ? redactWithdrawn(r) : r));
  }

  return jsonResponse(200, { items: filtered.sort((a, b) => b.date.localeCompare(a.date)) });
});
