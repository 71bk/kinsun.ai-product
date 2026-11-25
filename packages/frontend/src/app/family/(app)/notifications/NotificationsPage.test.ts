// @vitest-environment jsdom
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { ApiRequestError } from '@/lib/api/client';
import {
  getFamilyLinePreference,
  updateFamilyLinePreference,
  type FamilyLinePreference,
} from '@/lib/api/family-notifications';
import { getRuntimeConfig } from '@/lib/runtime-config';
import Page from './page';

vi.mock('@/lib/runtime-config', async (original) => ({
  ...(await original<typeof import('@/lib/runtime-config')>()),
  getRuntimeConfig: vi.fn(),
}));
vi.mock('@/lib/api/family-notifications', () => ({
  getFamilyLinePreference: vi.fn(),
  updateFamilyLinePreference: vi.fn(),
}));
const elderId = '30000000-0000-4000-8000-000000000001';
const result: FamilyLinePreference = {
  schema_version: '1.0',
  elder_id: elderId,
  preference_id: null,
  line_enabled: false,
  version: 0,
  frequency: 'DAILY',
  send_time_local: '08:00',
  timezone: 'Asia/Taipei',
  line_status: 'LINKED',
  availability: 'READY',
  can_enable: true,
  line_link_available: true,
  updated_at: null,
};
beforeEach(() => {
  vi.mocked(getRuntimeConfig).mockResolvedValue({
    apiBaseUrl: '/backend/core',
    elderId,
    caregiverId: '',
    consentPolicyVersion: '',
    credentialStatus: 'present',
  });
  vi.mocked(getFamilyLinePreference).mockResolvedValue(result);
  vi.mocked(updateFamilyLinePreference).mockResolvedValue({
    ...result,
    line_enabled: true,
    version: 1,
  });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
function mount() {
  return render(
    createElement(LocaleProvider, { initialLocale: 'en', children: createElement(Page) }),
  );
}
async function checkbox() {
  return screen.findByRole('checkbox') as Promise<HTMLInputElement>;
}

it('saves only this actor’s boolean and version, then reads the persisted setting', async () => {
  mount();
  fireEvent.click(await checkbox());
  vi.mocked(getFamilyLinePreference).mockResolvedValue({
    ...result,
    line_enabled: true,
    version: 1,
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save notification settings' }));
  await screen.findByText('Notification settings saved.');
  await waitFor(() => expect(screen.getByRole('checkbox').getAttribute('disabled')).toBeNull());
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
  expect(vi.mocked(updateFamilyLinePreference).mock.calls[0].slice(1, 4)).toEqual([
    elderId,
    true,
    0,
  ]);
  expect(getFamilyLinePreference).toHaveBeenCalledTimes(2);
});
it.each(['UNLINKED', 'RELINK_REQUIRED'] as const)(
  'requires receiving binding for %s',
  async (line_status) => {
    vi.mocked(getFamilyLinePreference).mockResolvedValue({
      ...result,
      line_status,
      can_enable: false,
      availability: 'LINE_LINK_REQUIRED',
    });
    mount();
    expect((await checkbox()).disabled).toBe(true);
    expect(screen.getByText(/Signing in with LINE may still require/)).toBeTruthy();
    expect(updateFamilyLinePreference).not.toHaveBeenCalled();
  },
);
it('allows opting out even when service is unavailable', async () => {
  vi.mocked(getFamilyLinePreference).mockResolvedValue({
    ...result,
    line_enabled: true,
    can_enable: false,
    availability: 'SERVICE_UNAVAILABLE',
    version: 2,
  });
  mount();
  const input = await checkbox();
  expect(input.disabled).toBe(false);
  fireEvent.click(input);
  fireEvent.click(screen.getByRole('button', { name: 'Save notification settings' }));
  await waitFor(() => expect(updateFamilyLinePreference).toHaveBeenCalled());
  expect(vi.mocked(updateFamilyLinePreference).mock.calls[0].slice(1, 4)).toEqual([
    elderId,
    false,
    2,
  ]);
});
it.each([403, 404])('removes settings on live access denial %s', async (status) => {
  mount();
  await checkbox();
  vi.mocked(getFamilyLinePreference).mockRejectedValue(
    new ApiRequestError(status, 'private denial'),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Refresh connection status' }));
  await screen.findByRole('alert');
  expect(screen.queryByRole('checkbox')).toBeNull();
  expect(document.body.textContent).not.toContain('private denial');
});
it('expires the session without leaving settings on screen', async () => {
  mount();
  fireEvent.click(await checkbox());
  vi.mocked(updateFamilyLinePreference).mockRejectedValue(
    new ApiRequestError(401, 'expired secret'),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Save notification settings' }));
  await screen.findByRole('link', { name: /sign.in/i });
  expect(screen.queryByRole('checkbox')).toBeNull();
});
it('reloads a conflicting version and requires another explicit save', async () => {
  mount();
  fireEvent.click(await checkbox());
  vi.mocked(updateFamilyLinePreference).mockRejectedValue(new ApiRequestError(409, 'conflict'));
  vi.mocked(getFamilyLinePreference).mockResolvedValue({ ...result, version: 5 });
  fireEvent.click(screen.getByRole('button', { name: 'Save notification settings' }));
  await screen.findByText(/Settings or receiving conditions changed/);
  await checkbox();
  expect(updateFamilyLinePreference).toHaveBeenCalledTimes(1);
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
});
it('does not duplicate an in-flight save and aborts it on unmount', async () => {
  vi.mocked(updateFamilyLinePreference).mockImplementation(() => new Promise(() => {}));
  const view = mount();
  const input = await checkbox();
  fireEvent.click(input);
  fireEvent.submit(input.closest('form')!);
  fireEvent.submit(input.closest('form')!);
  expect(updateFamilyLinePreference).toHaveBeenCalledTimes(1);
  const signal = vi.mocked(updateFamilyLinePreference).mock.calls[0][5];
  view.unmount();
  expect(signal?.aborted).toBe(true);
});
it('ignores an old read after the selected elder changes', async () => {
  let resolve!: (value: FamilyLinePreference) => void;
  vi.mocked(getFamilyLinePreference).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  mount();
  await waitFor(() => expect(getFamilyLinePreference).toHaveBeenCalledTimes(1));
  vi.mocked(getFamilyLinePreference).mockRejectedValue(new ApiRequestError(404, 'denied'));
  fireEvent(
    window,
    new StorageEvent('storage', { key: 'elderly_care_elder_id', newValue: 'other' }),
  );
  await screen.findByRole('alert');
  await act(async () => resolve(result));
  expect(screen.queryByRole('checkbox')).toBeNull();
});
