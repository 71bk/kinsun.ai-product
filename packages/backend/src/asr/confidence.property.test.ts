import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { ASR_CONFIDENCE_THRESHOLD, isConfidenceAcceptable } from './confidence.js';

/**
 * Feature: elderly-care-ai-companion, Property 2: 信心分數閾值分類.
 * For any confidence score, values below the threshold must trigger
 * degraded handling (ask-to-repeat at the ASR layer; needs_review at the
 * Event Extractor layer) and values at/above the threshold must proceed
 * normally.
 */
describe('Property 2: Confidence threshold classification', () => {
  it('classifies scores below threshold as unacceptable and at/above as acceptable', () => {
    fc.assert(
      fc.property(fc.float({ min: 0, max: 1, noNaN: true }), (confidence) => {
        const acceptable = isConfidenceAcceptable(confidence);
        expect(acceptable).toBe(confidence >= ASR_CONFIDENCE_THRESHOLD);
      }),
      { numRuns: 500 },
    );
  });

  it('respects a caller-supplied threshold override (used by Event Extractor needs_review gate)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1, noNaN: true }),
        fc.float({ min: 0, max: 1, noNaN: true }),
        (confidence, threshold) => {
          expect(isConfidenceAcceptable(confidence, threshold)).toBe(confidence >= threshold);
        },
      ),
      { numRuns: 500 },
    );
  });

  it('boundary: exactly at threshold is acceptable (>=, not >)', () => {
    expect(isConfidenceAcceptable(ASR_CONFIDENCE_THRESHOLD)).toBe(true);
  });
});
