/** OpenSearch Serverless index mappings — see design.md §OpenSearch Serverless 索引設計. */

export const HEALTH_KNOWLEDGE_INDEX_NAME = 'health-knowledge';

export const HEALTH_KNOWLEDGE_INDEX_MAPPING = {
  mappings: {
    properties: {
      chunk_id: { type: 'keyword' },
      document_id: { type: 'keyword' },
      content: { type: 'text' },
      content_vector: { type: 'knn_vector', dimension: 1024 },
      source_agency: { type: 'keyword' },
      document_title: { type: 'text' },
      service_type: { type: 'keyword' },
      region: { type: 'keyword' },
      effective_date: { type: 'date' },
      expiry_date: { type: 'date' },
      risk_level: { type: 'keyword' },
      review_status: { type: 'keyword' },
      version: { type: 'keyword' },
      chunk_index: { type: 'integer' },
      total_chunks: { type: 'integer' },
      created_at: { type: 'date' },
      updated_at: { type: 'date' },
    },
  },
} as const;

export const MEMORY_VECTORS_INDEX_NAME = 'memory-vectors';

export const MEMORY_VECTORS_INDEX_MAPPING = {
  mappings: {
    properties: {
      memory_id: { type: 'keyword' },
      elder_id: { type: 'keyword' },
      content: { type: 'text' },
      content_vector: { type: 'knn_vector', dimension: 1024 },
      category: { type: 'keyword' },
      is_active: { type: 'boolean' },
      created_at: { type: 'date' },
    },
  },
} as const;
