import { afterEach, describe, expect, it, vi } from 'vitest';
import { commandStaffReport, createReportFromSummary, type StaffReport } from './staff-reports';
const config = { apiBaseUrl: '/backend/core' };
function mockFetch() {
  const fetch = vi.fn<[RequestInfo | URL, RequestInit?], Promise<Response>>().mockResolvedValue(new Response(
    JSON.stringify({ data: {}, meta: { correlation_id: 'synthetic', timestamp: '2026-09-22T00:00:00Z', schema_version: '1.0' } }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  ));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
afterEach(() => { vi.unstubAllGlobals(); });
describe('staff report command contracts', () => {
  it('sends only the server-owned summary reference, expected version and recipient IDs', async () => {
    const fetch = mockFetch();
    await createReportFromSummary(config, 'elder', 'summary', 3, ['relationship'], 'retry-key');
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe('/backend/core/api/v1/elders/elder/family-reports/from-summary');
    expect(JSON.parse(String(options?.body))).toEqual({ summary_id: 'summary', expected_summary_version: 3,
      recipient_scope_ids: ['relationship'] });
    expect(new Headers(options?.headers).get('Idempotency-Key')).toBe('retry-key');
    expect(new Headers(options?.headers).has('Authorization')).toBe(false);
  });
  it.each(['publish', 'withdraw'] as const)('keeps %s within the selected elder and expected report version', async action => {
    const fetch = mockFetch();
    await commandStaffReport(config, 'elder', { report_id: 'report', version: 5 } as StaffReport, action, 'retry-key');
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe('/backend/core/api/v1/elders/elder/family-reports/report/' + action);
    expect(JSON.parse(String(options?.body))).toEqual({ expected_version: 5,
      reason_code: action === 'publish' ? 'CAREGIVER_UI_SAFETY_REVIEW' : 'CAREGIVER_UI_WITHDRAWAL',
      ...(action === 'publish' ? { safety_review_passed: true } : {}),
    });
  });
});
