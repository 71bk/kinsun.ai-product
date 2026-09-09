import { expect, it } from 'vitest';
import { parseSchedule } from './home-care-schedule';

const row = { assignment_id: '40000000-0000-4000-a000-000000000001', elder_id: '30000000-0000-4000-a000-000000000001', display_name: 'Synthetic Elder', scheduled_start: '2026-09-09T02:00:00Z', scheduled_end: '2026-09-09T03:00:00Z', status: 'CONFIRMED', timezone: 'Asia/Taipei', local_date: '2026-09-09' };
const fixture = () => ({ items: [{ ...row }], as_of: '2026-09-09T01:00:00Z', page: { next_cursor: null, has_more: false, limit: 20 } });

it('allows a minimal future confirmed preview and discards extra content', () => {
  const data = fixture();
  expect(parseSchedule({ ...data, items: [{ ...row, summary: 'must not leave parser', allowed_data_scopes: ['summary:read'] }] })).toEqual(data);
});
it.each(['DRAFT', 'COMPLETED', 'CANCELLED', 'EXPIRED', 'NO_SHOW'])('rejects non-preview state %s', (status) => {
  expect(() => parseSchedule({ ...fixture(), items: [{ ...row, status }] })).toThrow();
});
it.each([
  { scheduled_end: '2026-09-09T01:00:00Z' }, { scheduled_start: '2026-09-10T01:00:00Z' },
  { local_date: '2026-02-30' }, { local_date: '2026-09-10' }, { timezone: 'bad-zone' },
  { assignment_id: 'bad' }, { elder_id: 'bad' }, { display_name: '' }, { scheduled_start: '2026-09-09T02:00:00' },
])('rejects invalid schedule metadata %j', (change) => {
  expect(() => parseSchedule({ ...fixture(), items: [{ ...row, ...change }] })).toThrow();
});
it('rejects duplicate IDs and inconsistent pagination', () => {
  expect(() => parseSchedule({ ...fixture(), items: [row, row] })).toThrow();
  expect(() => parseSchedule({ ...fixture(), page: { next_cursor: null, has_more: true, limit: 20 } })).toThrow();
});
