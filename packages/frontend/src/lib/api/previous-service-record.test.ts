import { afterEach, expect, it, vi } from 'vitest';
import { getPreviousServiceRecord } from './service-records';
const config = { apiBaseUrl: '/backend/core' };
const note = {
  service_record_id: 'source',
  source_assignment_id: 'previous',
  service_date: '2026-09-13',
  service_timezone: 'Asia/Taipei',
  completed_at: '2026-09-13T01:00:00Z',
  version: 1,
  content: 'Synthetic',
};
function respond(value: unknown) {
  const fetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        data: value,
        meta: {
          correlation_id: 'synthetic',
          timestamp: '2026-09-14T00:00:00Z',
          schema_version: '1.0',
        },
      }),
      { status: 200 },
    ),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
afterEach(() => {
  vi.unstubAllGlobals();
});
it.each([null, note])('reads a bounded nullable result without caching', async (record) => {
  const fetch = respond({ assignment_id: 'current', record });
  expect(await getPreviousServiceRecord(config, 'current')).toEqual(record);
  expect(fetch).toHaveBeenCalledWith(
    '/backend/core/api/v1/home-care/assignments/current/previous-service-record',
    expect.objectContaining({ cache: 'no-store' }),
  );
});
it.each([
  { assignment_id: 'wrong', record: note },
  { assignment_id: 'current', record: { ...note, worker_id: 'hidden' } },
  { assignment_id: 'current', record: { ...note, source_assignment_id: 'current' } },
  { assignment_id: 'current', record: { ...note, content: 'x'.repeat(4001) } },
  { assignment_id: 'current', record: { ...note, version: null } },
  { assignment_id: 'current', record: { ...note, completed_at: 1 } },
  { assignment_id: 'current', record: { ...note, content: '' } },
  { assignment_id: 'current' },
  { assignment_id: 'current', record: null, total: 4 },
])('rejects malformed or excessive results', async (value) => {
  respond(value);
  await expect(getPreviousServiceRecord(config, 'current')).rejects.toMatchObject({ status: 502 });
});
