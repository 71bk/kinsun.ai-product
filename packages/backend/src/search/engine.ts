import type { MetadataFilter, SearchResult } from '@elderly-care/shared';
import type { Bm25SearchAdapter, VectorSearchAdapter } from './adapters.js';
import { filterValidResults } from './filter.js';
import { mergeAndDedup } from './hybrid.js';
import type { QueryReformulator } from './reformulate.js';

export interface SearchEngineDeps {
  bm25Adapter: Bm25SearchAdapter;
  vectorAdapter: VectorSearchAdapter;
  reformulator: QueryReformulator;
}

const DEFAULT_FILTER: MetadataFilter = { reviewStatus: 'approved' };

/**
 * SearchEngine (E01-E03) — reformulates the elder's spoken question,
 * fan-outs to BM25 + vector KNN in parallel, merges/dedups the results
 * (Property 14), and filters to only valid (approved, unexpired) documents
 * (Property 13) before handing results to the Reranker.
 */
export class SearchEngine {
  constructor(private readonly deps: SearchEngineDeps) {}

  async search(
    originalQuestion: string,
    filter: MetadataFilter = DEFAULT_FILTER,
    topK = 20,
  ): Promise<{ reformulatedQuery: string; results: SearchResult[] }> {
    const reformulatedQuery = await this.deps.reformulator.reformulate(originalQuestion);

    const [bm25Results, vectorResults] = await Promise.all([
      this.deps.bm25Adapter.search(reformulatedQuery, filter, topK),
      this.deps.vectorAdapter.search(reformulatedQuery, filter, topK),
    ]);

    const merged = mergeAndDedup(bm25Results, vectorResults);
    const valid = filterValidResults(merged);

    return { reformulatedQuery, results: valid };
  }
}
