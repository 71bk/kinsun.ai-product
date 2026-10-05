// @vitest-environment jsdom
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { apiFetch, ApiRequestError } from '@/lib/api/client';
import { getRuntimeConfig } from '@/lib/runtime-config';
import { askFamilyKnowledge, type FamilyKnowledgeAnswer } from '@/lib/api/family-knowledge';
import Page from './page';

vi.mock('@/lib/runtime-config', () => ({ getRuntimeConfig: vi.fn() }));
vi.mock('@/lib/api/family-knowledge', () => ({ askFamilyKnowledge: vi.fn() }));
vi.mock('@/lib/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/client')>()),
  apiFetch: vi.fn(),
}));
const result: FamilyKnowledgeAnswer = {
  status: 'ANSWER',
  answer: 'Synthetic <script>unsafe()</script>',
  sources: [
    {
      title: 'Synthetic official source',
      url: 'https://www.mohw.gov.tw/guide',
      locator: 'p. 3',
      current_status: 'unknown',
    },
  ],
};
beforeEach(() => {
  vi.mocked(getRuntimeConfig).mockResolvedValue({
    apiBaseUrl: '/backend/core/',
    credentialStatus: 'present',
  } as Awaited<ReturnType<typeof getRuntimeConfig>>);
  vi.mocked(apiFetch).mockResolvedValue({ role: 'FAMILY_MEMBER' });
  vi.mocked(askFamilyKnowledge).mockResolvedValue(result);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function mount() {
  return render(
    createElement(LocaleProvider, { initialLocale: 'en', children: createElement(Page) }),
  );
}
async function submit() {
  const field = await screen.findByRole('textbox');
  fireEvent.change(field, { target: { value: 'How do I apply?' } });
  fireEvent.submit(field.closest('form')!);
}
it('allows a family account without loading any elder records and renders escaped text with source links', async () => {
  const { container } = mount();
  await submit();
  expect(await screen.findByText(result.answer)).toBeTruthy();
  expect(container.querySelector('script')).toBeNull();
  expect(screen.getByRole('link', { name: 'Synthetic official source' }).getAttribute('href')).toBe(
    result.sources[0].url,
  );
  expect(apiFetch).toHaveBeenCalledTimes(1);
  expect(vi.mocked(apiFetch).mock.calls[0][1]).toBe('/api/v1/me');
  expect(vi.mocked(askFamilyKnowledge).mock.calls[0].slice(1, 3)).toEqual([
    'How do I apply?',
    'en-US',
  ]);
});
it.each(['ELDER', 'ADMIN', 'HOME_CARE_WORKER'])('does not expose the form to %s', async (role) => {
  vi.mocked(apiFetch).mockResolvedValue({ role });
  mount();
  await screen.findByRole('link', { name: /sign.in/i });
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(askFamilyKnowledge).not.toHaveBeenCalled();
});
it('prevents duplicate submissions and aborts an in-flight question when leaving', async () => {
  let resolve!: (value: FamilyKnowledgeAnswer) => void;
  vi.mocked(askFamilyKnowledge).mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const view = mount();
  await submit();
  fireEvent.submit(screen.getByRole('textbox').closest('form')!);
  expect(askFamilyKnowledge).toHaveBeenCalledTimes(1);
  const signal = vi.mocked(askFamilyKnowledge).mock.calls[0][3];
  view.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve(result));
  expect(screen.queryByText(result.answer)).toBeNull();
});
it('removes the previous answer if the family session expires', async () => {
  mount();
  await submit();
  await screen.findByText(result.answer);
  vi.mocked(askFamilyKnowledge).mockRejectedValue(
    new ApiRequestError(401, 'AUTHENTICATION_REQUIRED', 'Expired'),
  );
  await submit();
  await screen.findByRole('link', { name: /sign.in/i });
  expect(screen.queryByText(result.answer)).toBeNull();
});
it('uses a generic retry message without exposing provider errors', async () => {
  vi.mocked(askFamilyKnowledge).mockRejectedValue(new Error('private-provider-secret'));
  mount();
  await submit();
  await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
  expect(document.body.textContent).not.toContain('private-provider-secret');
});
