import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { ConsentRecord, ConsentRequest } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import { getAuthContext, jsonResponse, parseBody, requireAuthorization, withErrorHandling } from './http.js';

async function setConsent(elderId: string, type: ConsentRequest['type'], status: 'consented' | 'revoked') {
  const table = new DynamoTable();
  const now = new Date().toISOString();
  const record: ConsentRecord = {
    PK: Keys.elderPk(elderId),
    SK: Keys.consentSk(type),
    elderId,
    type,
    status,
    grantedAt: status === 'consented' ? now : null,
    revokedAt: status === 'revoked' ? now : null,
    updatedAt: now,
  };
  await table.putItem(record);
  return record;
}

/** POST /v1/consent/grant (A06.1, A06.3). Only the elder themself may grant/revoke their own consent. */
export const grantHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const { elderId, type } = parseBody<ConsentRequest>(event);
  requireAuthorization(authContext, 'event', 'read', elderId); // no dedicated "consent" resource — elder-scope check is what matters here
  if (authContext.role !== 'elder' && authContext.role !== 'admin') {
    return jsonResponse(403, { code: 'FORBIDDEN', message: 'Only the elder may grant consent' });
  }
  const record = await setConsent(elderId, type, 'consented');
  return jsonResponse(200, record);
});

/** POST /v1/consent/revoke (A06.4) — stops future recording; existing data follows the retention policy (H03). */
export const revokeHandler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const { elderId, type } = parseBody<ConsentRequest>(event);
  requireAuthorization(authContext, 'event', 'read', elderId);
  if (authContext.role !== 'elder' && authContext.role !== 'admin') {
    return jsonResponse(403, { code: 'FORBIDDEN', message: 'Only the elder may revoke consent' });
  }
  const record = await setConsent(elderId, type, 'revoked');
  return jsonResponse(200, record);
});
