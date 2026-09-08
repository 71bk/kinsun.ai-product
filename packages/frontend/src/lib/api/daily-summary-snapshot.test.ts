import { describe, expect, it } from 'vitest';
import { calendarDate, dailySummarySnapshot } from './daily-summary-snapshot';

const valid = {
  local_date: '2026-09-09', timezone: 'Asia/Taipei', as_of: '2026-09-08T16:00:00Z',
  summary: { summary_id: '11111111-1111-4111-a111-111111111111', status: 'DRAFT', version: 2 },
};

describe('daily summary metadata', () => {
  it.each(['DRAFT', 'READY', 'NEEDS_REVIEW', 'PUBLISHED', 'STALE', 'WITHDRAWN'])(
    'maps the precise workflow status %s', (status) => {
      expect(dailySummarySnapshot({ ...valid, summary: { ...valid.summary, status } })?.summary?.status).toBe(status);
    },
  );
  it('distinguishes a visible-day empty result from unavailable', () => {
    expect(dailySummarySnapshot({ ...valid, summary: null })).toEqual({
      localDate: valid.local_date, timezone: valid.timezone, asOf: valid.as_of, summary: null,
    });
  });
  it.each([null, undefined, {}, [], { ...valid, summary: undefined },
    { ...valid, local_date: '2026-02-30' }, { ...valid, local_date: '2026-09-08' },
    { ...valid, timezone: 'Unknown' }, { ...valid, as_of: '2026-09-08T16:00:00' },
    { ...valid, summary: { ...valid.summary, summary_id: '../private' } },
    { ...valid, summary: { ...valid.summary, status: 'GENERATING' } },
    { ...valid, summary: { ...valid.summary, version: 0 } },
    { ...valid, summary: { ...valid.summary, version: 1.5 } },
  ])('rejects invalid or incomplete metadata %j', (value) => {
    expect(dailySummarySnapshot(value)).toBeNull();
  });
  it.each(['2026-03-09T03:59:00Z', '2026-11-02T04:59:00Z'])('uses New York local date across DST %s', (asOf) => {
    const localDate = asOf.startsWith('2026-03') ? '2026-03-08' : '2026-11-01';
    expect(dailySummarySnapshot({ ...valid, as_of: asOf, timezone: 'America/New_York', local_date: localDate })?.localDate).toBe(localDate);
  });
  it.each(['2026-02-30', '2026-13-01', ['2026-09-08'], '2026-09-08&status=DRAFT', undefined])('does not trust query dates %j', (value) => {
    expect(calendarDate(value)).toBeUndefined();
  });
});
