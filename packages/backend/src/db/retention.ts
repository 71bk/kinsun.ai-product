/** Retention windows per design.md §資料保留政策. Shared by every writer that sets a `ttl` attribute. */
export const RETENTION_DAYS = {
  audio: 90,
  conversation: 365,
  event: 730,
  candidateMemory: 30,
  summary: 730,
  audit: 1095,
} as const;

export function computeTtlEpochSeconds(retentionDays: number, from: Date = new Date()): number {
  return Math.floor(from.getTime() / 1000) + retentionDays * 24 * 60 * 60;
}
