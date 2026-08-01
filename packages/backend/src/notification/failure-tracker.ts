import { DynamoTable, Keys } from '../db/index.js';

export const FAILURE_NOTIFICATION_THRESHOLD = 3;

const FAILURE_COUNT_SK = 'FAILURE_COUNT';

interface FailureCountRecord {
  PK: string;
  SK: string;
  elderId: string;
  consecutiveFailures: number;
  updatedAt: string;
}

export interface FailureCountStore {
  getItem<T>(pk: string, sk: string): Promise<T | null>;
  putItem<T extends object>(item: T): Promise<void>;
}

export interface RecordResult {
  count: number;
  /** True exactly once per failure streak — the call where count first reaches the threshold. */
  shouldNotify: boolean;
}

/**
 * FailureTracker (A01.5) — a success resets the streak to 0; a failure
 * increments it. `shouldNotify` fires only on the transition into the
 * threshold (count === FAILURE_NOTIFICATION_THRESHOLD), not on every
 * failure after — so a still-broken elder doesn't spam Family with a new
 * alert on every single subsequent attempt.
 */
export class FailureTracker {
  constructor(private readonly table: FailureCountStore = new DynamoTable()) {}

  async recordInteractionResult(elderId: string, success: boolean): Promise<RecordResult> {
    const pk = Keys.elderPk(elderId);
    const existing = await this.table.getItem<FailureCountRecord>(pk, FAILURE_COUNT_SK);
    const count = success ? 0 : (existing?.consecutiveFailures ?? 0) + 1;
    const shouldNotify = !success && count === FAILURE_NOTIFICATION_THRESHOLD;

    await this.table.putItem<FailureCountRecord>({
      PK: pk,
      SK: FAILURE_COUNT_SK,
      elderId,
      consecutiveFailures: count,
      updatedAt: new Date().toISOString(),
    });

    return { count, shouldNotify };
  }

  async getConsecutiveFailureCount(elderId: string): Promise<number> {
    const existing = await this.table.getItem<FailureCountRecord>(Keys.elderPk(elderId), FAILURE_COUNT_SK);
    return existing?.consecutiveFailures ?? 0;
  }
}
