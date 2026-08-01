import { InvokeCommand, LambdaClient } from '@aws-sdk/client-lambda';
import { SFNClient, StartSyncExecutionCommand } from '@aws-sdk/client-sfn';
import type { APIGatewayProxyResultV2, APIGatewayProxyWebsocketEventV2 } from 'aws-lambda';
import { ConnectionStore } from '../connection-store.js';
import { DEGRADATION_STRATEGIES } from '../degradation.js';
import { createErrorLog } from '../trace.js';
import { logError } from '../metrics.js';
import { postToConnection } from './ws-reply.js';

interface AudioMessage {
  audioBase64: string;
  encoding: 'pcm' | 'opus';
  sampleRate: number;
}

let sfnClient: SFNClient | null = null;
function getSfnClient(): SFNClient {
  if (!sfnClient) sfnClient = new SFNClient({});
  return sfnClient;
}

let lambdaClient: LambdaClient | null = null;
function getLambdaClient(): LambdaClient {
  if (!lambdaClient) lambdaClient = new LambdaClient({});
  return lambdaClient;
}

/**
 * Fire-and-forget async invoke of the post-processing Lambda (event
 * extraction + candidate memory generation) — matches design.md's
 * sequence diagram "par 非同步處理" branch. Never awaited by the caller and
 * never allowed to affect the elder-facing response; a failure here is
 * logged, not surfaced.
 */
async function triggerPostProcessing(
  elderId: string,
  traceId: string,
  conversationId: string,
  utterance: string,
  replyText: string,
): Promise<void> {
  const fnName = process.env.POST_PROCESSING_FUNCTION_NAME;
  if (!fnName || !utterance) return;
  try {
    await getLambdaClient().send(
      new InvokeCommand({
        FunctionName: fnName,
        InvocationType: 'Event',
        Payload: Buffer.from(JSON.stringify({ elderId, traceId, conversationId, utterance, replyText })),
      }),
    );
  } catch (err) {
    logError(
      createErrorLog({
        traceId,
        component: 'workflow',
        errorType: 'service_error',
        errorCode: 'POST_PROCESSING_INVOKE_FAILED',
        message: err instanceof Error ? err.message : 'unknown error invoking post-processing',
        elderId,
        retryAttempt: 0,
        resolved: false,
        fallbackAction: 'none',
      }),
    );
  }
}

/**
 * WebSocket `audio` route — the Router Lambda referenced in design.md
 * §協調層. Starts the voice-interaction Step Functions Express workflow
 * (see workflow/asl/voice-interaction.asl.json) synchronously and relays
 * its result back to the client. If the state machine isn't deployed yet
 * (STATE_MACHINE_ARN unset — true until tasks 5-8 wire the AI Lambdas),
 * degrades gracefully instead of throwing (A05.1).
 */
export async function handler(
  event: APIGatewayProxyWebsocketEventV2,
): Promise<APIGatewayProxyResultV2> {
  const connectionId = event.requestContext.connectionId;
  const store = new ConnectionStore();
  const connection = await store.get(connectionId);
  if (!connection) {
    return { statusCode: 401, body: 'Unknown connection' };
  }
  if (!connection.conversationId || !connection.traceId) {
    return { statusCode: 400, body: 'Session not started — send a control "start" message first' };
  }

  const stateMachineArn = process.env.STATE_MACHINE_ARN;
  if (!stateMachineArn) {
    await postToConnection(event.requestContext, {
      type: 'response',
      ...DEGRADATION_STRATEGIES.all_retries_exhausted,
    });
    return { statusCode: 200, body: 'Degraded: workflow not yet deployed' };
  }

  const message = JSON.parse(event.body ?? '{}') as AudioMessage;

  try {
    const result = await getSfnClient().send(
      new StartSyncExecutionCommand({
        stateMachineArn,
        name: `${connection.traceId}_${Date.now()}`,
        input: JSON.stringify({
          elderId: connection.elderId,
          conversationId: connection.conversationId,
          traceId: connection.traceId,
          audio: message,
        }),
      }),
    );

    const output = result.output ? JSON.parse(result.output) : { degraded: true, response: '系統忙碌中，請稍後再試' };
    await postToConnection(event.requestContext, { type: 'response', ...output });

    void triggerPostProcessing(connection.elderId, connection.traceId, connection.conversationId, output.transcript ?? '', output.response ?? '');

    return { statusCode: 200, body: 'OK' };
  } catch (err) {
    logError(
      createErrorLog({
        traceId: connection.traceId,
        component: 'workflow',
        errorType: 'service_error',
        errorCode: 'SFN_START_FAILED',
        message: err instanceof Error ? err.message : 'unknown error starting workflow',
        elderId: connection.elderId,
        retryAttempt: 0,
        resolved: false,
        fallbackAction: 'all_retries_exhausted',
      }),
    );
    await postToConnection(event.requestContext, {
      type: 'response',
      ...DEGRADATION_STRATEGIES.all_retries_exhausted,
    });
    return { statusCode: 200, body: 'Degraded' };
  }
}
