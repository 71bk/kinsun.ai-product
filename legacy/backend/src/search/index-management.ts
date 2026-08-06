import { Client } from '@opensearch-project/opensearch';
import { HEALTH_KNOWLEDGE_INDEX_MAPPING, HEALTH_KNOWLEDGE_INDEX_NAME, MEMORY_VECTORS_INDEX_MAPPING, MEMORY_VECTORS_INDEX_NAME } from './index-mappings.js';

function getEndpoint(): string {
  const endpoint = process.env.OPENSEARCH_ENDPOINT;
  if (!endpoint) throw new Error('OPENSEARCH_ENDPOINT is not configured');
  return endpoint;
}

let cachedClient: Client | null = null;
export function getOpenSearchClient(): Client {
  if (!cachedClient) {
    cachedClient = new Client({ node: getEndpoint() });
  }
  return cachedClient;
}

/** Index lifecycle management (E03.1) — create/update/rebuild the two indices this system depends on. */
export class IndexManager {
  constructor(private readonly client: Client = getOpenSearchClient()) {}

  async createIndex(name: string, mapping: Record<string, unknown>): Promise<void> {
    const exists = await this.client.indices.exists({ index: name });
    if (exists.body) return;
    await this.client.indices.create({ index: name, body: mapping });
  }

  async createHealthKnowledgeIndex(): Promise<void> {
    await this.createIndex(HEALTH_KNOWLEDGE_INDEX_NAME, HEALTH_KNOWLEDGE_INDEX_MAPPING);
  }

  async createMemoryVectorsIndex(): Promise<void> {
    await this.createIndex(MEMORY_VECTORS_INDEX_NAME, MEMORY_VECTORS_INDEX_MAPPING);
  }

  async deleteIndex(name: string): Promise<void> {
    await this.client.indices.delete({ index: name });
  }

  /** Rebuilds an index under a new name and marks it ready for cutover (G03.2). */
  async rebuildIndex(name: string, mapping: Record<string, unknown>): Promise<string> {
    const newName = `${name}-${Date.now()}`;
    await this.createIndex(newName, mapping);
    return newName;
  }
}
