// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ElderSessionPage from './page';

const api = vi.hoisted(() => ({
  acknowledgeTabletFirstUse: vi.fn(),
  endTabletSession: vi.fn(),
  getCurrentTabletSession: vi.fn(),
  revokeTabletFirstUseAcknowledgement: vi.fn(),
  runAssistedCompanionTurn: vi.fn(),
}));
const router = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('@/lib/api/assisted-elders', () => api);

const required = {
  status: 'REQUIRED' as const,
  policy_version: 'demo-consent-v1',
  consent_version: null,
  acknowledged_at: null,
  confirmation_method: null,
};
const acknowledged = {
  status: 'ACKNOWLEDGED' as const,
  policy_version: 'demo-consent-v1',
  consent_version: 1,
  acknowledged_at: '2026-09-01T04:00:00Z',
  confirmation_method: 'ASSISTED_TABLET_ACKNOWLEDGEMENT' as const,
};

function tabletSession(firstUse: typeof required | typeof acknowledged = required) {
  return {
    assisted_session_id: '79000000-0000-4000-8000-000000000001',
    elder_id: '75000000-0000-4000-8000-000000000001',
    display_name: '測試長者',
    preferred_name: '林奶奶',
    status: 'ACTIVE' as const,
    idle_expires_at: '2026-09-01T04:30:00Z',
    absolute_expires_at: '2026-09-01T12:00:00Z',
    first_use_acknowledgement: firstUse,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  api.getCurrentTabletSession.mockResolvedValue(tabletSession());
  api.endTabletSession.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
});

describe('Elder Session first-use acknowledgement', () => {
  it('blocks chat until the plain-language acknowledgement is recorded', async () => {
    render(createElement(ElderSessionPage));

    expect(await screen.findByRole('heading', { name: '林奶奶，開始前先說明' })).toBeTruthy();
    expect(screen.queryByLabelText('想對小暖說的話')).toBeNull();
    expect(screen.getByText(/疾病、用藥與注意事項目前不會送給 AI/)).toBeTruthy();
    expect(screen.queryByText('糖尿病')).toBeNull();
  });

  it('opens chat only after the server confirms acknowledgement', async () => {
    api.acknowledgeTabletFirstUse.mockResolvedValue(acknowledged);
    render(createElement(ElderSessionPage));

    fireEvent.click(await screen.findByRole('button', { name: /了解並開始使用/ }));

    expect(await screen.findByLabelText('想對小暖說的話')).toBeTruthy();
    expect(api.acknowledgeTabletFirstUse).toHaveBeenCalledOnce();
    expect(window.scrollTo).toHaveBeenCalledWith({ behavior: 'auto', left: 0, top: 0 });
  });

  it('keeps chat blocked when acknowledgement cannot be recorded', async () => {
    api.acknowledgeTabletFirstUse.mockRejectedValue(new Error('synthetic failure'));
    render(createElement(ElderSessionPage));

    fireEvent.click(await screen.findByRole('button', { name: /了解並開始使用/ }));

    expect((await screen.findByRole('alert')).textContent).toContain('尚未開始使用 AI');
    expect(screen.queryByLabelText('想對小暖說的話')).toBeNull();
    expect(window.scrollTo).not.toHaveBeenCalled();
  });

  it('requires a second action before revoking and returns to the notice', async () => {
    api.getCurrentTabletSession.mockResolvedValue(tabletSession(acknowledged));
    api.revokeTabletFirstUseAcknowledgement.mockResolvedValue(required);
    render(createElement(ElderSessionPage));

    fireEvent.click(await screen.findByRole('button', { name: '停止 AI 陪伴' }));
    expect(api.revokeTabletFirstUseAcknowledgement).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /確定停止 AI 陪伴/ }));

    await waitFor(() => {
      expect(api.revokeTabletFirstUseAcknowledgement).toHaveBeenCalledOnce();
    });
    expect(await screen.findByRole('heading', { name: '林奶奶，開始前先說明' })).toBeTruthy();
    expect(screen.queryByLabelText('想對小暖說的話')).toBeNull();
    expect(window.scrollTo).toHaveBeenCalledWith({ behavior: 'auto', left: 0, top: 0 });
  });
});
