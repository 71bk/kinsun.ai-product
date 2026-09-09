import { ApiRequestError, apiFetch, type ApiConfig } from './client';
import { calendarDate } from './daily-summary-snapshot';

export interface ScheduleItem {
  assignment_id: string;
  elder_id: string;
  display_name: string;
  scheduled_start: string;
  scheduled_end: string;
  status: 'CONFIRMED' | 'IN_PROGRESS';
  timezone: string;
  local_date: string;
}
export interface SchedulePage {
  items: ScheduleItem[];
  as_of: string;
  page: { next_cursor: string | null; has_more: boolean; limit: number };
}
const timestamp = (v: unknown): v is string => typeof v === 'string' &&
  /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const uuid = (v: unknown): v is string => typeof v === 'string' &&
  /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(v);

export function parseSchedule(raw: unknown): SchedulePage {
  const fail = (): never => { throw new ApiRequestError(502, 'Invalid schedule response'); };
  if (!raw || typeof raw !== 'object') return fail();
  const value = raw as SchedulePage;
  if (!timestamp(value.as_of) || !Array.isArray(value.items) || value.items.length > 100 ||
      !value.page || typeof value.page.has_more !== 'boolean' ||
      !Number.isInteger(value.page.limit) || value.page.limit < 1 || value.page.limit > 100 ||
      value.items.length > value.page.limit ||
      (value.page.next_cursor !== null && (typeof value.page.next_cursor !== 'string' || !value.page.next_cursor)) ||
      value.page.has_more !== (value.page.next_cursor !== null)) return fail();
  const seen = new Set<string>();
  const items = value.items.map((row) => {
    if (!row || !uuid(row.assignment_id) || seen.has(row.assignment_id) || !uuid(row.elder_id) ||
        typeof row.display_name !== 'string' || !row.display_name.trim() ||
        !timestamp(row.scheduled_start) || !timestamp(row.scheduled_end) ||
        Date.parse(row.scheduled_end) <= Math.max(Date.parse(value.as_of), Date.parse(row.scheduled_start)) ||
        !['CONFIRMED', 'IN_PROGRESS'].includes(row.status) || !calendarDate(row.local_date) ||
        typeof row.timezone !== 'string') return fail();
    try {
      const day = new Intl.DateTimeFormat('en-CA', { timeZone: row.timezone, year: 'numeric', month: '2-digit', day: '2-digit' });
      if (day.format(new Date(value.as_of)) !== row.local_date ||
          day.format(new Date(row.scheduled_start)) > row.local_date) return fail();
    } catch { return fail(); }
    seen.add(row.assignment_id);
    // Deliberate allowlist: previews never carry summary, scopes or clinical content.
    return { assignment_id: row.assignment_id, elder_id: row.elder_id, display_name: row.display_name,
      scheduled_start: row.scheduled_start, scheduled_end: row.scheduled_end,
      status: row.status, timezone: row.timezone, local_date: row.local_date };
  });
  return { items, as_of: value.as_of, page: { next_cursor: value.page.next_cursor, has_more: value.page.has_more, limit: value.page.limit } };
}

export async function getHomeCareSchedule(config: ApiConfig, cursor?: string): Promise<SchedulePage> {
  return parseSchedule(await apiFetch<unknown>(config,
    `/api/v1/me/home-care-schedule?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`));
}
