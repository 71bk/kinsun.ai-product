// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ApiRequestError } from '@/lib/api/client';
import * as api from '@/lib/api/elder-profiles';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { ElderProfilePanel } from './ElderProfilePanel';

vi.mock('@/lib/api/elder-profiles');
const config = { apiBaseUrl: '/backend/core' };
const access = vi.fn();
const nameChanged = vi.fn();
const profile: api.ElderProfile = {
  elder_id: 'elder',
  display_name: 'Synthetic elder',
  preferred_name: null,
  preferred_language: 'ZH_TW',
  profile_version: 2,
};
const record: api.CareProfileEntry = {
  care_profile_entry_id: 'entry',
  elder_id: 'elder',
  category: 'ALLERGY',
  content: 'Synthetic care information',
  source_type: 'STAFF_RECORDED',
  source_actor_id: 'actor',
  verification_status: 'RECORDED',
  effective_from: '2026-09-29T01:00:00Z',
  retired_at: null,
  version: 3,
  created_at: '2026-09-29T01:00:00Z',
  updated_at: '2026-09-29T01:00:00Z',
};
const permissions = [
  'elder:basic:read',
  'care_profile:read',
  'elder:profile:update',
  'care_profile:write',
];
function setup(actions = permissions) {
  return render(
    createElement(LocaleProvider, {
      initialLocale: 'en',
      children: createElement(ElderProfilePanel, {
        config,
        elderId: 'elder',
        allowedActions: actions,
        onAccessCheck: access,
        onNameChanged: nameChanged,
      }),
    }),
  );
}
beforeEach(() => {
  vi.mocked(api.getElderProfile).mockResolvedValue(profile);
  vi.mocked(api.listCareProfile).mockResolvedValue({
    items: [record],
    next_cursor: null,
    has_more: false,
  });
  vi.mocked(api.listProfileHistory).mockResolvedValue({
    items: [],
    next_cursor: null,
    has_more: false,
  });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('filters retired records on the server and preserves an unrelated basic draft', async () => {
  setup();
  fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Unsaved name' } });
  expect(api.listCareProfile).toHaveBeenCalledWith(config, 'elder', false);
  fireEvent.click(screen.getByRole('checkbox', { name: 'Include retired records' }));
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
  await waitFor(() => expect(api.listCareProfile).toHaveBeenCalledWith(config, 'elder', true));
  expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Unsaved name');
});

it('shows read-only data without granting write controls and never reads ungranted care data', async () => {
  setup(['elder:basic:read']);
  const name = (await screen.findByLabelText('Name')) as HTMLInputElement;
  expect(name.disabled).toBe(true);
  expect(screen.queryByRole('button', { name: 'Save changes' })).toBeNull();
  expect(api.listCareProfile).not.toHaveBeenCalled();
  expect(api.listProfileHistory).not.toHaveBeenCalled();
});

it('saves expected version, trims names and reports the saved name to the page header', async () => {
  vi.mocked(api.updateElderProfile).mockResolvedValue({
    ...profile,
    display_name: 'Corrected',
    profile_version: 3,
  });
  setup();
  fireEvent.change(await screen.findByLabelText('Name'), { target: { value: ' Corrected ' } });
  fireEvent.change(screen.getByLabelText('Reason for this change'), {
    target: { value: ' Correction ' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByText('Saved. Change history has been updated.');
  expect(api.updateElderProfile).toHaveBeenCalledWith(
    config,
    'elder',
    {
      display_name: 'Corrected',
      preferred_name: null,
      preferred_language: 'ZH_TW',
      reason: 'Correction',
      expected_version: 2,
    },
    expect.any(String),
  );
  expect(nameChanged).toHaveBeenCalledWith('Corrected');
});

it('preserves a conflicting draft and only discards it after reload confirmation', async () => {
  vi.mocked(api.updateElderProfile).mockRejectedValue(
    new ApiRequestError(409, 'private raw detail', 'CONFLICT'),
  );
  setup();
  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Unsaved correction' },
  });
  fireEvent.change(screen.getByLabelText('Reason for this change'), {
    target: { value: 'Correction' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByRole('alert');
  expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Unsaved correction');
  expect(screen.queryByText('private raw detail')).toBeNull();
  expect((screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement).disabled).toBe(
    true,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Discard unsaved changes and reload' }));
  expect(api.getElderProfile).toHaveBeenCalledTimes(1);
  fireEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Discard unsaved changes and reload',
    }),
  );
  await waitFor(() =>
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Synthetic elder'),
  );
});

it('reuses the same idempotency key after uncertain failure', async () => {
  vi.mocked(api.updateElderProfile).mockRejectedValue(
    new ApiRequestError(503, 'unavailable', 'UNAVAILABLE'),
  );
  setup();
  await screen.findByLabelText('Name');
  fireEvent.change(screen.getByLabelText('Reason for this change'), {
    target: { value: 'Correction' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(api.updateElderProfile).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.updateElderProfile).mock.calls[0][3]).toBe(
    vi.mocked(api.updateElderProfile).mock.calls[1][3],
  );
});

it('requires a reason and explicit confirmation before retirement', async () => {
  vi.mocked(api.retireCareProfile).mockResolvedValue({
    ...record,
    version: 4,
    verification_status: 'RETIRED',
  });
  setup();
  fireEvent.click(await screen.findByRole('button', { name: 'Retire' }));
  const form = within(screen.getByRole('form', { name: 'Retire' }));
  expect((form.getByRole('button', { name: 'Retire' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(form.getByLabelText('Reason for this change'), {
    target: { value: 'No longer used' },
  });
  fireEvent.click(form.getByRole('button', { name: 'Retire' }));
  expect(api.retireCareProfile).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Retire' }));
  await waitFor(() =>
    expect(api.retireCareProfile).toHaveBeenCalledWith(
      config,
      'elder',
      'entry',
      { expected_version: 3, reason: 'No longer used' },
      expect.any(String),
    ),
  );
});

it('clears content, draft and dialogs immediately after access loss', async () => {
  vi.mocked(api.updateElderProfile).mockRejectedValue(
    new ApiRequestError(404, 'denied', 'NOT_FOUND'),
  );
  setup();
  await screen.findByText('Synthetic care information');
  fireEvent.change(screen.getByLabelText('Reason for this change'), {
    target: { value: 'Correction' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(access).toHaveBeenCalledOnce());
  expect(screen.queryByText('Synthetic care information')).toBeNull();
  expect(screen.queryByLabelText('Name')).toBeNull();
});
