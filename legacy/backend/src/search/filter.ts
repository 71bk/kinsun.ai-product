import type { SearchResult } from '@elderly-care/shared';

/**
 * Property 13 (搜尋結果有效性過濾): a result is valid only if it's been
 * approved (never needs_review/rejected) and hasn't expired. This is
 * enforced both as an OpenSearch query-time filter (defense at the source)
 * and again here as a result-set filter (defense at the boundary) — so a
 * misconfigured query can never leak an invalid document past this
 * function.
 */
export function isResultValid(result: SearchResult, now: Date = new Date()): boolean {
  if (result.metadata.reviewStatus !== 'approved') return false;
  if (result.metadata.expiryDate && new Date(result.metadata.expiryDate).getTime() < now.getTime()) return false;
  return true;
}

export function filterValidResults(results: SearchResult[], now: Date = new Date()): SearchResult[] {
  return results.filter((r) => isResultValid(r, now));
}
