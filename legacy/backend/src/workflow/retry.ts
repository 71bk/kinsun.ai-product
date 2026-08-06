import type { RetryPolicy } from '@elderly-care/shared';
import { GLOBAL_MAX_RETRIES } from './nodes.js';

/**
 * Tracks per-node and interaction-wide retry counts for one workflow
 * execution. Property 3 requires that neither bound is ever exceeded no
 * matter what sequence of errors a node throws.
 */
export class RetryTracker {
  private readonly attemptsByNode = new Map<string, number>();
  private totalRetries = 0;

  constructor(private readonly globalMaxRetries: number = GLOBAL_MAX_RETRIES) {}

  getNodeAttempts(nodeId: string): number {
    return this.attemptsByNode.get(nodeId) ?? 0;
  }

  getTotalRetries(): number {
    return this.totalRetries;
  }

  /**
   * Call after a node execution fails with a retryable error. Returns true
   * if a retry is permitted (and records it); false if either the node's
   * own maxAttempts or the global cap has been reached, in which case the
   * caller must fall back (see degradation.ts) instead of retrying.
   */
  recordFailureAndCheckRetry(nodeId: string, policy: RetryPolicy): boolean {
    const nodeAttempts = this.getNodeAttempts(nodeId);
    // maxAttempts counts *retries*, i.e. attempts after the first try.
    if (nodeAttempts >= policy.maxAttempts) return false;
    if (this.totalRetries >= this.globalMaxRetries) return false;

    this.attemptsByNode.set(nodeId, nodeAttempts + 1);
    this.totalRetries += 1;
    return true;
  }

  backoffSeconds(policy: RetryPolicy, nodeId: string): number {
    const attempt = this.getNodeAttempts(nodeId);
    return policy.intervalSeconds * Math.pow(policy.backoffRate, Math.max(0, attempt - 1));
  }
}

export function isRetryableError(policy: RetryPolicy, errorCode: string): boolean {
  return policy.retryableErrors.includes(errorCode);
}
