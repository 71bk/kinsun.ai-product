// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AssistedVoiceCompanion } from './AssistedVoiceCompanion';

const mocks = vi.hoisted(() => ({
  open: vi.fn(), capture: vi.fn(), dispose: vi.fn(), current: vi.fn(), turn: vi.fn(), prompt: vi.fn(),
}));
vi.mock('@/lib/voice/hands-free-recorder', () => ({ HandsFreeRecorder: class {
  open = mocks.open;
  capture = mocks.capture;
  dispose = mocks.dispose;
} }));
vi.mock('@/lib/api/assisted-elders', () => ({ getCurrentTabletSession: mocks.current }));
vi.mock('@/lib/voice/assisted-voice-turn', () => ({ runAssistedVoiceTurn: mocks.turn }));
vi.mock('@/lib/voice/assisted-prompt', () => ({ playRetryPrompt: mocks.prompt }));

function setup() {
  const callbacks = { onEnd: vi.fn(async () => {}), onReply: vi.fn(), onActiveChange: vi.fn() };
  const view = render(createElement(AssistedVoiceCompanion, { assistedSessionId: 'handoff', ...callbacks }));
  fireEvent.click(screen.getByRole('button', { name: '開啟語音陪伴' }));
  return { ...view, ...callbacks };
}
beforeEach(() => {
  vi.resetAllMocks();
  mocks.open.mockResolvedValue(undefined);
  mocks.current.mockResolvedValue({ assisted_session_id: 'handoff', first_use_acknowledgement: { status: 'ACKNOWLEDGED' } });
});
afterEach(cleanup);

describe('assisted voice microphone lifecycle', () => {
  it('stops capture immediately on pause and releases the device on unmount', async () => {
    let signal: AbortSignal | undefined;
    mocks.capture.mockImplementation((value: AbortSignal) => {
      signal = value;
      return new Promise((_resolve, reject) => value.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError'))));
    });
    const view = setup();
    await waitFor(() => expect(mocks.capture).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: '暫停收音與播放' }));
    expect(signal?.aborted).toBe(true);
    expect(mocks.dispose).toHaveBeenCalled();
    expect(view.onActiveChange).toHaveBeenLastCalledWith(false);
    await act(async () => {});
    view.unmount();
    expect(mocks.turn).not.toHaveBeenCalled();
  });

  it('releases permission granted after leaving without starting capture', async () => {
    let grant!: () => void;
    mocks.open.mockReturnValue(new Promise<void>((resolve) => { grant = resolve; }));
    const view = setup();
    view.unmount();
    await act(async () => grant());
    expect(mocks.dispose).toHaveBeenCalled();
    expect(mocks.capture).not.toHaveBeenCalled();
  });

  it('rejects a replaced or expired tablet before any capture', async () => {
    mocks.current.mockResolvedValue({ assisted_session_id: 'replacement', first_use_acknowledgement: { status: 'ACKNOWLEDGED' } });
    const view = setup();
    await screen.findByRole('alert');
    expect(mocks.capture).not.toHaveBeenCalled();
    expect(mocks.dispose).toHaveBeenCalled();
    expect(view.onActiveChange).toHaveBeenLastCalledWith(false);
  });

  it('caps silence at two segments and closes the microphone', async () => {
    mocks.capture.mockResolvedValue(null);
    setup();
    await screen.findByText('暫時沒有聽到說話，麥克風已暫停。請照服員協助重新開啟。');
    expect(mocks.capture).toHaveBeenCalledTimes(2);
    expect(mocks.dispose).toHaveBeenCalled();
    expect(mocks.turn).not.toHaveBeenCalled();
  });

  it('ends the tablet session on a spoken stop', async () => {
    mocks.capture.mockResolvedValue(new Blob(['synthetic']));
    mocks.turn.mockResolvedValue({ kind: 'stop' });
    const view = setup();
    await waitFor(() => expect(view.onEnd).toHaveBeenCalledTimes(1));
    expect(mocks.dispose).toHaveBeenCalled();
    expect(mocks.capture).toHaveBeenCalledTimes(1);
    expect(view.onReply).not.toHaveBeenCalled();
  });

  it('preserves the displayed reply and pauses if synthesis fails', async () => {
    mocks.capture.mockResolvedValue(new Blob(['synthetic']));
    mocks.turn.mockResolvedValue({ kind: 'reply', text: '合成測試回覆', audioUrl: null });
    const view = setup();
    await screen.findByText('回覆已顯示，但目前無法播放語音。麥克風已暫停，請照服員協助。');
    expect(view.onReply).toHaveBeenCalledWith('合成測試回覆');
    expect(mocks.capture).toHaveBeenCalledTimes(1);
    expect(mocks.dispose).toHaveBeenCalled();
  });
});
