import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import type { HealthSearchRequest } from '@elderly-care/shared';
import { OpenSearchBm25Adapter, OpenSearchVectorAdapter } from '../search/adapters.js';
import { SearchEngine } from '../search/engine.js';
import { HealthAnswerGenerator } from '../search/answer.js';
import { BedrockQueryReformulator } from '../search/reformulate.js';
import { getAuthContext, jsonResponse, parseBody, requireAuthorization, withErrorHandling } from './http.js';

let cachedGenerator: HealthAnswerGenerator | null = null;
function getAnswerGenerator(): HealthAnswerGenerator {
  if (!cachedGenerator) {
    const searchEngine = new SearchEngine({
      bm25Adapter: new OpenSearchBm25Adapter(),
      vectorAdapter: new OpenSearchVectorAdapter(),
      reformulator: new BedrockQueryReformulator(),
    });
    cachedGenerator = new HealthAnswerGenerator({ searchEngine });
  }
  return cachedGenerator;
}

/** POST /v1/search/health (E01, E05) — grounded, cited health-education answers. */
export const handler = withErrorHandling(async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
  const authContext = getAuthContext(event);
  const { elderId, question } = parseBody<HealthSearchRequest>(event);
  requireAuthorization(authContext, 'summary', 'read', elderId); // no dedicated "health_query" resource — read-level access to the elder is the bar

  const response = await getAnswerGenerator().answer(question);
  return jsonResponse(200, response);
});
