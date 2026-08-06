import type { ElderProfile } from '@elderly-care/shared';
import { DynamoTable } from '../db/index.js';
import { SummaryGenerator } from './generator.js';

export interface DailySummaryEvent {
  /** Explicit elder list (e.g. for a retry/backfill invocation); omitted for the normal EventBridge-scheduled run. */
  elderIds?: string[];
  /** ISO date (YYYY-MM-DD); defaults to "today" in UTC. */
  date?: string;
}

function todayUtcDate(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * EventBridge-scheduled Lambda entrypoint (B02.1) — generates one daily
 * summary per elder. A single elder's failure is logged and skipped rather
 * than aborting the whole batch, so one bad day for one elder doesn't
 * withhold every other elder's summary.
 */
export async function handler(event: DailySummaryEvent = {}): Promise<{ generated: number; failed: number }> {
  const table = new DynamoTable();
  const generator = new SummaryGenerator(table);
  const date = event.date ?? todayUtcDate();

  const elderIds = event.elderIds ?? (await table.scanBySk<ElderProfile>('PROFILE')).map((p) => p.elderId);

  let generated = 0;
  let failed = 0;
  for (const elderId of elderIds) {
    try {
      await generator.generateDailySummary(elderId, date);
      generated++;
    } catch (err) {
      failed++;
      console.error(`[summary] failed to generate summary for elder ${elderId}`, err instanceof Error ? err.message : err);
    }
  }

  return { generated, failed };
}
