import type { SearchResult } from '@elderly-care/shared';

interface MergedEntry {
  base: SearchResult;
  bm25Score: number;
  vectorScore: number;
}

/**
 * Property 14 (搜尋結果去重): merges BM25 and vector-KNN result sets keyed
 * by chunk_id — the Map guarantees no duplicate chunk_id can survive — while
 * preserving each side's own score. A chunk found by only one method gets a
 * 0 for the other method's score rather than being dropped.
 */
export function mergeAndDedup(bm25Results: SearchResult[], vectorResults: SearchResult[]): SearchResult[] {
  const merged = new Map<string, MergedEntry>();

  for (const r of bm25Results) {
    merged.set(r.chunkId, { base: r, bm25Score: r.bm25Score, vectorScore: 0 });
  }
  for (const r of vectorResults) {
    const existing = merged.get(r.chunkId);
    if (existing) {
      existing.vectorScore = r.vectorScore;
    } else {
      merged.set(r.chunkId, { base: r, bm25Score: 0, vectorScore: r.vectorScore });
    }
  }

  return Array.from(merged.values()).map(({ base, bm25Score, vectorScore }) => ({
    ...base,
    bm25Score,
    vectorScore,
    combinedScore: bm25Score + vectorScore,
  }));
}
