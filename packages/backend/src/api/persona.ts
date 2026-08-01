import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { PersonaRecord, UpdatePersonaRequest } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import { getAuthContext, jsonResponse, parseBody, requireAuthorization, requirePathParam, withErrorHandling } from './http.js';

/** PUT /v1/elders/{elderId}/persona (A06 prerequisite for personalization; caregiver/admin only). */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const elderId = requirePathParam(event, 'elderId');
  requireAuthorization(authContext, 'persona', 'write', elderId);

  const updates = parseBody<UpdatePersonaRequest>(event);
  const table = new DynamoTable();
  const existing = await table.getItem<PersonaRecord>(Keys.elderPk(elderId), Keys.personaSk());

  const merged: PersonaRecord = {
    PK: Keys.elderPk(elderId),
    SK: 'PERSONA',
    elderId,
    displayName: updates.displayName ?? existing?.displayName ?? '',
    preferredLanguage: updates.preferredLanguage ?? existing?.preferredLanguage ?? 'zh-TW',
    responseLength: updates.responseLength ?? existing?.responseLength ?? 'medium',
    speakingSpeed: updates.speakingSpeed ?? existing?.speakingSpeed ?? 'normal',
    interactionStyle: updates.interactionStyle ?? existing?.interactionStyle ?? 'warm',
    customGreeting: updates.customGreeting ?? existing?.customGreeting ?? '',
    updatedAt: new Date().toISOString(),
    updatedBy: updates.updatedBy,
  };

  await table.putItem(merged);
  return jsonResponse(200, merged);
});
