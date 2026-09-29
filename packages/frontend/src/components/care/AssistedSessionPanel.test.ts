// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AssistedSessionPanel } from './AssistedSessionPanel';
const api = vi.hoisted(() => ({ issueAssistedSession: vi.fn(), recordAssistedVerbalAcknowledgement: vi.fn() }));
vi.mock('@/lib/api/assisted-elders', () => api);
beforeEach(() => {
  vi.resetAllMocks();
  api.issueAssistedSession.mockResolvedValue({ assisted_session_id: 'handoff-a', pairing_token: 'one-time-pairing', pairing_expires_at: new Date(Date.now() + 600000).toISOString() });
  api.recordAssistedVerbalAcknowledgement.mockResolvedValue({ status: 'ACKNOWLEDGED' });
});
afterEach(() => { cleanup(); });
it('requires a staff-recorded expression of agreement before tablet delivery', async () => {
  render(createElement(AssistedSessionPanel, { config: { apiBaseUrl: '/backend/core' }, elderId: 'elder-a', elderName: '合成長者' }));
  fireEvent.click(screen.getByRole('button', { name: '準備陪伴平板' }));
  const confirm = await screen.findByRole('button', { name: '記錄長者口頭確認' }) as HTMLButtonElement;
  expect(confirm.disabled).toBe(true);
  expect(api.recordAssistedVerbalAcknowledgement).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(confirm);
  expect(await screen.findByRole('link', { name: '在這台裝置開啟長者模式' })).toBeTruthy();
  expect(api.recordAssistedVerbalAcknowledgement).toHaveBeenCalledWith({ apiBaseUrl: '/backend/core' }, 'elder-a', 'handoff-a');
  fireEvent.click(screen.getByRole('button', { name: '重新準備平板' }));
  await waitFor(() => expect(api.issueAssistedSession).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole('link', { name: '在這台裝置開啟長者模式' })).toBeNull();
});
it('does not offer delivery after a failed acknowledgement', async () => {
  api.recordAssistedVerbalAcknowledgement.mockRejectedValue(new Error('unavailable'));
  render(createElement(AssistedSessionPanel, { config: { apiBaseUrl: '/backend/core' }, elderId: 'elder-a', elderName: '合成長者' }));
  fireEvent.click(screen.getByRole('button', { name: '準備陪伴平板' }));
  fireEvent.click(await screen.findByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', { name: '記錄長者口頭確認' }));
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.queryByRole('link')).toBeNull();
});
