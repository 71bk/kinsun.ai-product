import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { RetryPolicy } from '@elderly-care/shared';
import { GLOBAL_MAX_RETRIES } from './nodes.js';
import { RetryTracker } from './retry.js';

const retryPolicyArb = fc.record({
  maxAttempts: fc.integer({ min: 0, max: 5 }),
  intervalSeconds: fc.integer({ min: 0, max: 5 }),
  backoffRate: fc.integer({ min: 1, max: 3 }),
  retryableErrors: fc.constant(['ANY']),
});

/**
 * Feature: elderly-care-ai-companion, Property 3: 有限重試上界 (bounded retries).
 * For any sequence of errors during one workflow execution, a single node's
 * retry count never exceeds that node's configured maxAttempts, and the
 * interaction's total retry count never exceeds the global cap.
 */
describe('Property 3: Finite retry upper bound', () => {
  it('never exceeds a node maxAttempts even under an unbounded failure stream', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 8 }),
        retryPolicyArb,
        fc.integer({ min: 0, max: 50 }), // number of consecutive failures thrown at this node
        (nodeId, policy, failureCount) => {
          const tracker = new RetryTracker();
          let grantedRetries = 0;
          for (let i = 0; i < failureCount; i++) {
            if (tracker.recordFailureAndCheckRetry(nodeId, policy)) {
              grantedRetries++;
            } else {
              break; // caller must stop retrying and fall back once denied
            }
          }
          expect(grantedRetries).toBeLessThanOrEqual(policy.maxAttempts);
          expect(tracker.getNodeAttempts(nodeId)).toBeLessThanOrEqual(policy.maxAttempts);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('never exceeds the global retry cap across many nodes failing in the same interaction', () => {
    fc.assert(
      fc.property(
        fc.array(fc.tuple(fc.string({ minLength: 1, maxLength: 8 }), retryPolicyArb), {
          minLength: 1,
          maxLength: 10,
        }),
        (nodesWithPolicies) => {
          const tracker = new RetryTracker();
          for (const [nodeId, policy] of nodesWithPolicies) {
            // Hammer each node with far more failures than it could ever need.
            for (let i = 0; i < 20; i++) {
              tracker.recordFailureAndCheckRetry(nodeId, policy);
            }
          }
          expect(tracker.getTotalRetries()).toBeLessThanOrEqual(GLOBAL_MAX_RETRIES);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('a maxAttempts of 0 grants zero retries', () => {
    const tracker = new RetryTracker();
    const policy: RetryPolicy = { maxAttempts: 0, intervalSeconds: 0, backoffRate: 1, retryableErrors: [] };
    expect(tracker.recordFailureAndCheckRetry('n1', policy)).toBe(false);
  });
});
