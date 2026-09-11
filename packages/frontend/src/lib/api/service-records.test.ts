import { afterEach, expect, it, vi } from 'vitest';
import {
  getServiceRecord,
  submitServiceRecord,
  submitServiceRecordAndComplete,
} from './service-records';

const config = { apiBaseUrl: '/backend/core' };
const data = {
  service_record_id: 'record',
  assignment_id: 'visit',
  content: 'Synthetic note',
  service_date: '2026-09-09',
  service_timezone: 'Asia/Taipei',
  completed_at: '2026-09-09T01:00:00Z',
  status: 'COMPLETED',
  version: 1,
  tenant_id: 'not-for-ui',
};
function response(value = data) {
  return new Response(
    JSON.stringify({
      data: value,
      meta: {
        correlation_id: 'synthetic',
        timestamp: '2026-09-09T01:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status: 200 },
  );
}
afterEach(() => {
  vi.unstubAllGlobals();
});
it('uses same-origin BFF, no-store, and drops fields not needed by the UI', async () => {
  const fetch = vi.fn().mockResolvedValue(response());
  vi.stubGlobal('fetch', fetch);
  const result = await getServiceRecord(config, 'visit');
  expect(result).not.toHaveProperty('tenant_id');
  expect(fetch).toHaveBeenCalledWith(
    '/backend/core/api/v1/home-care/assignments/visit/service-record',
    expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }),
  );
});
it('preserves caller-owned retry keys and only sends command fields', async () => {
  const fetch = vi.fn().mockResolvedValue(response());
  vi.stubGlobal('fetch', fetch);
  await submitServiceRecord(
    config,
    'visit',
    { content: 'Synthetic note', expected_assignment_version: 2 },
    'same-key',
  );
  const init = fetch.mock.calls[0][1];
  expect(new Headers(init.headers).get('Idempotency-Key')).toBe('same-key');
  expect(JSON.parse(init.body)).toEqual({
    content: 'Synthetic note',
    expected_assignment_version: 2,
    record_type: 'SERVICE_NOTE',
  });
});
it.each([
  { ...data, assignment_id: 'other' },
  { ...data, status: 'DRAFT' },
  { ...data, content: 'x'.repeat(4001) },
])('rejects invalid or cross-assignment responses', async (value) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(value)));
  await expect(getServiceRecord(config, 'visit')).rejects.toMatchObject({ status: 502 });
});

const completion = {
  service_record_id: 'record',
  assignment_id: 'visit',
  assignment_version: 3,
  status: 'COMPLETED',
};
function completionResponse(value: unknown = completion) {
  return new Response(
    JSON.stringify({
      data: value,
      meta: {
        correlation_id: 'synthetic',
        timestamp: '2026-09-11T00:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status: 201 },
  );
}
it('submits one atomic command and keeps the retry key with a content-free receipt', async () => {
  const fetch = vi.fn().mockResolvedValue(completionResponse());
  vi.stubGlobal('fetch', fetch);
  expect(
    await submitServiceRecordAndComplete(
      config,
      'visit',
      { expected_assignment_version: 2, content: 'Synthetic' },
      'same-key',
    ),
  ).toEqual(completion);
  const [url, init] = fetch.mock.calls[0];
  expect(url).toBe('/backend/core/api/v1/home-care/assignments/visit/service-record/complete');
  expect(new Headers(init.headers).get('Idempotency-Key')).toBe('same-key');
  expect(JSON.parse(init.body)).toEqual({
    expected_assignment_version: 2,
    content: 'Synthetic',
    record_type: 'SERVICE_NOTE',
  });
});
it.each([
  { ...completion, assignment_id: 'other' },
  { ...completion, assignment_version: 2 },
  { ...completion, status: 'IN_PROGRESS' },
  { ...completion, content: 'Synthetic forbidden note' },
])('rejects a malformed or content-bearing completion receipt', async (value) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(completionResponse(value)));
  await expect(
    submitServiceRecordAndComplete(
      config,
      'visit',
      { expected_assignment_version: 2, content: 'Synthetic' },
      'same-key',
    ),
  ).rejects.toMatchObject({ status: 502 });
});
