import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type {
  CaregiverDashboardEntry,
  CaregiverDashboardResponse,
  ConversationRecord,
  ElderProfile,
  EventRecord,
} from '@elderly-care/shared';
import { DynamoTable, GSI2, Keys } from '../db/index.js';
import { getAuthContext, jsonResponse, requirePathParam, withErrorHandling } from './http.js';

function todayUtcDate(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * GET /v1/caregivers/{caregiverId}/dashboard (C01.1-C01.3). Only ever
 * enumerates elders under CG#{caregiverId} -> ELDER# mappings, so a
 * caregiver structurally cannot see an elder they aren't assigned —
 * there's no "elderIds" input to this handler that a client could widen.
 */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const caregiverId = requirePathParam(event, 'caregiverId');
  if (authContext.role !== 'admin' && authContext.userId !== caregiverId) {
    return jsonResponse(403, { code: 'FORBIDDEN', message: 'Cannot view another caregiver\'s dashboard' });
  }

  const table = new DynamoTable();
  const mappings = await table.queryByPk<{ elderId: string }>(Keys.caregiverPk(caregiverId), 'ELDER#');
  const today = todayUtcDate();

  const elders: CaregiverDashboardEntry[] = await Promise.all(
    mappings.map(async ({ elderId }) => {
      const [profile, conversations, todaysSummary, pendingReview] = await Promise.all([
        table.getItem<ElderProfile>(Keys.elderPk(elderId), Keys.profileSk()),
        table.queryByPk<ConversationRecord>(Keys.elderPk(elderId), Keys.conversationSkPrefix()),
        table.getItem<unknown>(Keys.elderPk(elderId), Keys.summarySk(today)),
        table.queryGsi2<EventRecord>(GSI2.pk(elderId, 'needs_review')),
      ]);

      const lastInteractionAt = conversations.reduce<string | null>(
        (latest, c) => (!latest || c.startTime > latest ? c.startTime : latest),
        null,
      );
      const todayInteractionCount = conversations.filter((c) => c.startTime.startsWith(today)).length;

      const entry: CaregiverDashboardEntry = {
        elderId,
        elderName: profile?.name ?? elderId,
        lastInteractionAt,
        todayInteractionCount,
        summaryStatus: todaysSummary ? 'generated' : 'pending',
        pendingReviewCount: pendingReview.length,
      };
      return entry;
    }),
  );

  const response: CaregiverDashboardResponse = { elders };
  return jsonResponse(200, response);
});
