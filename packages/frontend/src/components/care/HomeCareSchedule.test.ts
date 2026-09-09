// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { ApiRequestError } from '@/lib/api/client';
import { getHomeCareSchedule, type SchedulePage } from '@/lib/api/home-care-schedule';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { HomeCareSchedule } from './HomeCareSchedule';

vi.mock('@/lib/api/home-care-schedule', () => ({ getHomeCareSchedule: vi.fn() }));
const load = vi.mocked(getHomeCareSchedule);
const config = { apiBaseUrl: '/backend/core' };
const fixture = (): SchedulePage => ({ as_of: '2026-09-09T01:00:00Z', page: { next_cursor: null, has_more: false, limit: 20 }, items: [{ assignment_id: 'synthetic-assignment', elder_id: 'synthetic-elder', display_name: 'Synthetic Future Elder', status: 'CONFIRMED', scheduled_start: '2026-09-09T02:00:00Z', scheduled_end: '2026-09-09T03:00:00Z', timezone: 'Asia/Taipei', local_date: '2026-09-09' }] });
function mount(locale: 'en' | 'zh-Hant' = 'en', onAccessCheck = vi.fn()) {
  return render(createElement(LocaleProvider, { initialLocale: locale, children: createElement(HomeCareSchedule, { config, onAccessCheck }) }));
}
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); });
it.each(['en', 'zh-Hant'] as const)('shows minimal preview without detail links or commands: %s', async (locale) => {
  load.mockResolvedValue(fixture());
  mount(locale);
  await screen.findByText('Synthetic Future Elder');
  expect(screen.queryByRole('link')).toBeNull();
  expect(screen.getByText(locale === 'en' ? 'Assignment confirmed' : '已確認派案')).toBeDefined();
});
it('replaces old page and ignores a late response after refresh', async () => {
  let resolve!: (value: SchedulePage) => void;
  load.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  mount();
  load.mockResolvedValue({ ...fixture(), items: [] });
  fireEvent.click(screen.getByRole('button', { name: 'Refresh schedule' }));
  await screen.findByText('No viewable assignments for today.');
  await act(async () => resolve(fixture()));
  expect(screen.queryByText('Synthetic Future Elder')).toBeNull();
});
it.each([401, 403, 404])('drops data and requests owner reauthorization: %s', async (status) => {
  const check = vi.fn();
  load.mockResolvedValue(fixture());
  mount('en', check);
  await screen.findByText('Synthetic Future Elder');
  load.mockRejectedValue(new ApiRequestError(status, 'Denied'));
  fireEvent.click(screen.getByRole('button', { name: 'Refresh schedule' }));
  expect(screen.queryByText('Synthetic Future Elder')).toBeNull();
  await screen.findByRole('alert');
  expect(check).toHaveBeenCalledOnce();
});
it('clears expired rows and reloads using server-relative time', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
  const data = fixture(); data.items[0].scheduled_end = '2026-09-09T01:00:01Z';
  load.mockResolvedValueOnce(data).mockResolvedValue({ ...data, items: [] });
  mount();
  await act(async () => {});
  expect(screen.getByText('Synthetic Future Elder')).toBeDefined();
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(screen.queryByText('Synthetic Future Elder')).toBeNull();
  expect(load).toHaveBeenCalledTimes(2);
});
it('replaces pagination instead of retaining possibly revoked earlier rows', async () => {
  load.mockResolvedValueOnce({ ...fixture(), page: { next_cursor: 'opaque', has_more: true, limit: 20 } });
  mount();
  await screen.findByText('Synthetic Future Elder');
  load.mockResolvedValue({ ...fixture(), items: [] });
  fireEvent.click(screen.getByRole('button', { name: 'Next schedule page' }));
  expect(screen.queryByText('Synthetic Future Elder')).toBeNull();
  await screen.findByText('No viewable assignments for today.');
  expect(load).toHaveBeenLastCalledWith(config, 'opaque');
});
it('clears data on hidden and discards pending hidden-page results', async () => {
  let resolve!: (value: SchedulePage) => void;
  load.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  mount();
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  fireEvent(document, new Event('visibilitychange'));
  await act(async () => resolve(fixture()));
  expect(screen.queryByText('Synthetic Future Elder')).toBeNull();
  hidden.mockRestore();
});
