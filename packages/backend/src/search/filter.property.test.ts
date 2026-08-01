import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { filterValidResults } from './filter.js';
import { searchResultArb } from './search-result.test-arbitraries.js';

const NOW = new Date('2026-07-24T00:00:00Z');

/**
 * Feature: elderly-care-ai-companion, Property 13: 搜尋結果有效性過濾.
 * For any set of documents with mixed review_status/dates, the filtered
 * results never include a needs_review (or rejected) document, and never
 * include a document whose effective_date range has expired.
 */
describe('Property 13: Search result validity filtering', () => {
  it('never returns a non-approved document', () => {
    fc.assert(
      fc.property(fc.array(searchResultArb(), { maxLength: 30 }), (results) => {
        const filtered = filterValidResults(results, NOW);
        for (const r of filtered) {
          expect(r.metadata.reviewStatus).toBe('approved');
        }
      }),
      { numRuns: 200 },
    );
  });

  it('never returns an expired document', () => {
    fc.assert(
      fc.property(fc.array(searchResultArb(), { maxLength: 30 }), (results) => {
        const filtered = filterValidResults(results, NOW);
        for (const r of filtered) {
          if (r.metadata.expiryDate) {
            expect(new Date(r.metadata.expiryDate).getTime()).toBeGreaterThanOrEqual(NOW.getTime());
          }
        }
      }),
      { numRuns: 200 },
    );
  });

  it('keeps every approved, unexpired document (no false negatives)', () => {
    fc.assert(
      fc.property(fc.array(searchResultArb(), { maxLength: 30 }), (results) => {
        const filtered = filterValidResults(results, NOW);
        const filteredIds = new Set(filtered.map((r) => r.chunkId));
        for (const r of results) {
          const isValid =
            r.metadata.reviewStatus === 'approved' &&
            (!r.metadata.expiryDate || new Date(r.metadata.expiryDate).getTime() >= NOW.getTime());
          if (isValid) {
            expect(filteredIds.has(r.chunkId)).toBe(true);
          }
        }
      }),
      { numRuns: 200 },
    );
  });
});
