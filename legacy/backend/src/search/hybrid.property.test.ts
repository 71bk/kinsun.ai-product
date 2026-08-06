import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { mergeAndDedup } from './hybrid.js';
import { searchResultArb } from './search-result.test-arbitraries.js';

const chunkIdPool = fc.constantFrom('c1', 'c2', 'c3', 'c4', 'c5'); // small pool forces overlap

/**
 * Feature: elderly-care-ai-companion, Property 14: 搜尋結果去重.
 * For any BM25 and vector-KNN result sets with overlapping chunk_ids, the
 * merged set never contains two entries with the same chunk_id, and every
 * merged entry retains both its bm25Score and vectorScore.
 */
describe('Property 14: Search result deduplication', () => {
  it('the merged result set never contains a duplicate chunkId', () => {
    fc.assert(
      fc.property(
        fc.array(searchResultArb(chunkIdPool), { maxLength: 15 }),
        fc.array(searchResultArb(chunkIdPool), { maxLength: 15 }),
        (bm25Results, vectorResults) => {
          const merged = mergeAndDedup(bm25Results, vectorResults);
          const ids = merged.map((r) => r.chunkId);
          expect(new Set(ids).size).toBe(ids.length);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('a chunk present in both sources keeps its bm25Score from BM25 and vectorScore from vector search', () => {
    fc.assert(
      fc.property(
        fc.array(searchResultArb(chunkIdPool), { minLength: 1, maxLength: 15 }),
        fc.array(searchResultArb(chunkIdPool), { minLength: 1, maxLength: 15 }),
        (bm25Results, vectorResults) => {
          const merged = mergeAndDedup(bm25Results, vectorResults);
          const bm25ById = new Map(bm25Results.map((r) => [r.chunkId, r]));
          const vectorById = new Map(vectorResults.map((r) => [r.chunkId, r]));

          for (const entry of merged) {
            const fromBm25 = bm25ById.get(entry.chunkId);
            const fromVector = vectorById.get(entry.chunkId);
            expect(entry.bm25Score).toBe(fromBm25 ? fromBm25.bm25Score : 0);
            expect(entry.vectorScore).toBe(fromVector ? fromVector.vectorScore : 0);
            expect(entry.combinedScore).toBeCloseTo(entry.bm25Score + entry.vectorScore, 5);
          }
        },
      ),
      { numRuns: 200 },
    );
  });

  it('every chunkId from either source appears exactly once in the merged output', () => {
    fc.assert(
      fc.property(
        fc.array(searchResultArb(chunkIdPool), { maxLength: 15 }),
        fc.array(searchResultArb(chunkIdPool), { maxLength: 15 }),
        (bm25Results, vectorResults) => {
          const merged = mergeAndDedup(bm25Results, vectorResults);
          const mergedIds = new Set(merged.map((r) => r.chunkId));
          const expectedIds = new Set([...bm25Results.map((r) => r.chunkId), ...vectorResults.map((r) => r.chunkId)]);
          expect(mergedIds).toEqual(expectedIds);
        },
      ),
      { numRuns: 200 },
    );
  });
});
