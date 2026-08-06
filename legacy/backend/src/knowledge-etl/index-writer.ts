import { Client } from '@opensearch-project/opensearch';
import { BedrockRuntimeClient } from '@aws-sdk/client-bedrock-runtime';
import type { DocumentMetadata } from '@elderly-care/shared';
import { embedText } from '../search/embeddings.js';
import { HEALTH_KNOWLEDGE_INDEX_NAME } from '../search/index-mappings.js';
import { getOpenSearchClient } from '../search/index-management.js';
import type { DocumentChunk } from './chunking.js';

export interface IndexWriterDeps {
  client?: Client;
  bedrockClient?: BedrockRuntimeClient;
}

/** Embeds and writes chunks into the health-knowledge OpenSearch index (G02.1's final stage). */
export class KnowledgeIndexWriter {
  private readonly client: Client;
  private readonly bedrockClient: BedrockRuntimeClient;

  constructor(deps: IndexWriterDeps = {}) {
    this.client = deps.client ?? getOpenSearchClient();
    this.bedrockClient = deps.bedrockClient ?? new BedrockRuntimeClient({});
  }

  async writeChunks(chunks: DocumentChunk[], metadata: DocumentMetadata, documentTitle: string): Promise<void> {
    for (const chunk of chunks) {
      const vector = await embedText(this.bedrockClient, chunk.content);
      await this.client.index({
        index: HEALTH_KNOWLEDGE_INDEX_NAME,
        id: chunk.chunkId,
        body: {
          chunk_id: chunk.chunkId,
          document_id: chunk.documentId,
          content: chunk.content,
          content_vector: vector,
          source_agency: metadata.sourceAgency,
          document_title: documentTitle,
          service_type: metadata.serviceType,
          region: metadata.region,
          effective_date: metadata.effectiveDate,
          expiry_date: metadata.expiryDate,
          risk_level: metadata.riskLevel,
          review_status: metadata.reviewStatus,
          version: metadata.version,
          chunk_index: chunk.chunkIndex,
          total_chunks: chunk.totalChunks,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      });
    }
  }

  /** Marks every chunk of a document as failed/superseded (G03.2) — used when rebuilding or retiring a version. */
  async markDocumentExpired(documentId: string, expiryDate: string): Promise<void> {
    await this.client.updateByQuery({
      index: HEALTH_KNOWLEDGE_INDEX_NAME,
      body: {
        query: { term: { document_id: documentId } },
        script: { source: 'ctx._source.expiry_date = params.expiryDate', params: { expiryDate } },
      },
    });
  }
}
