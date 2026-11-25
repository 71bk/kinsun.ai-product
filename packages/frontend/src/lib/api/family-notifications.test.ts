import { afterEach, expect, it, vi } from 'vitest';
import { apiFetch } from './client';
import { getFamilyLinePreference, updateFamilyLinePreference } from './family-notifications';
vi.mock('./client', async (original) => ({
  ...(await original<typeof import('./client')>()),
  apiFetch: vi.fn(),
}));
const config = { apiBaseUrl: '/backend/core' };
const elderId = '30000000-0000-4000-8000-000000000001';
const dto = {
  schema_version: '1.0',
  elder_id: elderId,
  preference_id: null,
  line_enabled: false,
  version: 0,
  frequency: 'DAILY',
  send_time_local: '08:00',
  timezone: 'Asia/Taipei',
  line_status: 'UNLINKED',
  availability: 'LINE_LINK_REQUIRED',
  can_enable: false,
  line_link_available: true,
  updated_at: null,
};
afterEach(() => {
  vi.resetAllMocks();
});
it('uses the cookie BFF with an explicit own-setting command', async () => {
  vi.mocked(apiFetch).mockResolvedValue(dto);
  await updateFamilyLinePreference(config, elderId, false, 0, 'synthetic-key');
  const init = vi.mocked(apiFetch).mock.calls[0][2]!;
  expect(init.method).toBe('PUT');
  expect(init.headers).toEqual({ 'Idempotency-Key': 'synthetic-key' });
  expect(JSON.parse(init.body as string)).toEqual({ line_enabled: false, expected_version: 0 });
});
it.each([
  { transcript: 'private' },
  { encrypted_external_subject: 'private' },
  { actor_id: elderId },
  { elder_id: '30000000-0000-4000-8000-000000000002' },
  { version: -1 },
  { line_enabled: 'true' },
  { timezone: 'UTC' },
  { can_enable: true },
  { line_status: 'UNKNOWN' },
])('rejects unsafe or malformed raw payload %j', async (changes) => {
  vi.mocked(apiFetch).mockResolvedValue({ ...dto, ...changes });
  await expect(getFamilyLinePreference(config, elderId)).rejects.toThrow();
});
