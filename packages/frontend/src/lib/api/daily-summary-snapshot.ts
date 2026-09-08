import type { CoreSummaryStatus } from './summaries';

export interface DailySummarySnapshot {
  localDate: string;
  timezone: string;
  asOf: string;
  summary: { summaryId: string; status: CoreSummaryStatus; version: number } | null;
}

export function calendarDate(value: unknown): string | undefined {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
    ? value : undefined;
}

export function dailySummarySnapshot(value: unknown): DailySummarySnapshot | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const wire = value as Record<string, unknown>;
  const localDate = calendarDate(wire.local_date);
  if (!localDate || typeof wire.timezone !== 'string' || typeof wire.as_of !== 'string' ||
      !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(wire.as_of) || !Number.isFinite(Date.parse(wire.as_of))) return null;
  try {
    const parts = new Intl.DateTimeFormat('en', {
      timeZone: wire.timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(new Date(wire.as_of));
    const part = (type: string) => parts.find((item) => item.type === type)?.value;
    if (`${part('year')}-${part('month')}-${part('day')}` !== localDate) return null;
  } catch { return null; }
  const base = { localDate, timezone: wire.timezone, asOf: wire.as_of };
  if (wire.summary === null) return { ...base, summary: null };
  if (!wire.summary || typeof wire.summary !== 'object' || Array.isArray(wire.summary)) return null;
  const summary = wire.summary as Record<string, unknown>;
  const statuses: CoreSummaryStatus[] = ['DRAFT', 'READY', 'NEEDS_REVIEW', 'PUBLISHED', 'STALE', 'WITHDRAWN'];
  if (typeof summary.summary_id !== 'string' ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(summary.summary_id) ||
      !statuses.includes(summary.status as CoreSummaryStatus) ||
      typeof summary.version !== 'number' || !Number.isSafeInteger(summary.version) || summary.version < 1) return null;
  return { ...base, summary: {
    summaryId: summary.summary_id, status: summary.status as CoreSummaryStatus, version: summary.version,
  } };
}
