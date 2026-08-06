import { BedrockRuntimeClient, InvokeModelCommand } from '@aws-sdk/client-bedrock-runtime';

const DEFAULT_EMBEDDING_MODEL_ID = process.env.BEDROCK_EMBEDDING_MODEL_ID ?? 'amazon.titan-embed-text-v2:0';

/** Shared embedding call — used by both vector search (query time) and the knowledge ETL pipeline (index time). */
export async function embedText(
  client: BedrockRuntimeClient,
  text: string,
  modelId: string = DEFAULT_EMBEDDING_MODEL_ID,
): Promise<number[]> {
  const response = await client.send(
    new InvokeModelCommand({
      modelId,
      contentType: 'application/json',
      body: JSON.stringify({ inputText: text }),
    }),
  );
  const payload = JSON.parse(Buffer.from(response.body).toString('utf-8'));
  return payload.embedding as number[];
}
