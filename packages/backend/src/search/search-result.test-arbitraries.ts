import fc from 'fast-check';
import type { DocumentMetadata, SearchResult } from '@elderly-care/shared';

export const reviewStatusArb = fc.constantFrom<DocumentMetadata['reviewStatus']>('needs_review', 'approved', 'rejected');

export function metadataArb(): fc.Arbitrary<DocumentMetadata> {
  return fc.record({
    sourceAgency: fc.constantFrom('衛生福利部', '國民健康署', '地方衛生局'),
    serviceType: fc.constant('health'),
    region: fc.constant('TW'),
    effectiveDate: fc.constant('2020-01-01'),
    expiryDate: fc.option(fc.constantFrom('2020-01-01', '2099-01-01'), { nil: null }),
    riskLevel: fc.constantFrom('low', 'medium', 'high'),
    reviewStatus: reviewStatusArb,
    version: fc.constant('1'),
  });
}

export function searchResultArb(chunkIdArb: fc.Arbitrary<string> = fc.uuid()): fc.Arbitrary<SearchResult> {
  return fc.record({
    chunkId: chunkIdArb,
    documentId: fc.uuid(),
    content: fc.string({ minLength: 1, maxLength: 100 }),
    sourceAgency: fc.constantFrom('衛生福利部', '國民健康署', '地方衛生局'),
    documentTitle: fc.constant('長者衛教手冊'),
    publishDate: fc.constant('2020-01-01'),
    bm25Score: fc.float({ min: 0, max: 10, noNaN: true }),
    vectorScore: fc.float({ min: 0, max: 1, noNaN: true }),
    combinedScore: fc.float({ min: 0, max: 11, noNaN: true }),
    metadata: metadataArb(),
  });
}
