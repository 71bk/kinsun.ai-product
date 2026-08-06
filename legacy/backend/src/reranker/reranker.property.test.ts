import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { searchResultArb } from '../search/search-result.test-arbitraries.js';
import { Reranker } from './reranker.js';

const NOW = new Date('2026-07-24T00:00:00Z');

/**
 * Feature: elderly-care-ai-companion, Property 15: Reranker Top-N 截斷.
 * For any ranked result set and any N, the number of results sent to the
 * LLM equals min(N, available results), and they are exactly the N
 * highest-rerankScore results — never an arbitrary subset.
 */
describe('Property 15: Reranker top-N truncation', () => {
  it('returns exactly min(n, available) results', () => {
    fc.assert(
      fc.property(fc.array(searchResultArb(), { maxLength: 20 }), fc.integer({ min: 0, max: 25 }), (results, n) => {
        const reranker = new Reranker();
        const ranked = reranker.rerank('query', results, undefined, NOW);
        const top = reranker.topN(ranked, n);
        expect(top.length).toBe(Math.min(n, results.length));
      }),
      { numRuns: 200 },
    );
  });

  it('returns precisely the N highest-scoring results, in descending order', () => {
    fc.assert(
      fc.property(fc.array(searchResultArb(), { minLength: 1, maxLength: 20 }), fc.integer({ min: 0, max: 20 }), (results, n) => {
        const reranker = new Reranker();
        const ranked = reranker.rerank('query', results, undefined, NOW);
        const top = reranker.topN(ranked, n);

        const sortedScores = ranked.map((r) => r.rerankScore).sort((a, b) => b - a);
        const expectedTopScores = sortedScores.slice(0, n);

        expect(top.map((r) => r.rerankScore)).toEqual(expectedTopScores);
        // Descending order within the returned slice.
        for (let i = 1; i < top.length; i++) {
          expect(top[i - 1]!.rerankScore).toBeGreaterThanOrEqual(top[i]!.rerankScore);
        }
      }),
      { numRuns: 200 },
    );
  });

  it('every returned result carries its full rankingFactors breakdown', () => {
    fc.assert(
      fc.property(fc.array(searchResultArb(), { minLength: 1, maxLength: 10 }), (results) => {
        const reranker = new Reranker();
        const ranked = reranker.rerank('query', results, undefined, NOW);
        for (const r of ranked) {
          expect(r.rankingFactors.queryRelevance).toBeGreaterThanOrEqual(0);
          expect(r.rankingFactors.sourceCredibility).toBeGreaterThanOrEqual(0);
          expect(r.rankingFactors.recency).toBeGreaterThanOrEqual(0);
        }
      }),
      { numRuns: 100 },
    );
  });
});
