import type { DocumentMetadata } from '@elderly-care/shared';
import type { DocumentManifest } from './manifest.js';

/**
 * Tags a chunk with the metadata OpenSearch filters on. Every newly
 * imported document defaults to review_status = 'needs_review' (G02.2) —
 * there is no code path in this function that can produce 'approved'; that
 * transition only happens through the separate human-review step (task 19
 * caregiver/content-manager UI), never automatically at import time.
 */
export function tagMetadata(manifest: DocumentManifest): DocumentMetadata {
  return {
    sourceAgency: manifest.sourceAgency,
    serviceType: manifest.serviceType,
    region: manifest.region,
    effectiveDate: manifest.effectiveDate,
    expiryDate: manifest.expiryDate ?? null,
    riskLevel: manifest.riskLevel,
    reviewStatus: 'needs_review',
    version: manifest.version,
  };
}
