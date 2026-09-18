// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement, StrictMode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { CompanionTurn } from '@/lib/api/companion';

const mocks = vi.hoisted(() => ({ synthesize: vi.fn() }));
vi.mock('@/lib/voice/speech-gateway-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/voice/speech-gateway-client')>()),
  synthesizeSpeech: mocks.synthesize,
}));
import { CompanionReplyAudio } from './CompanionReplyAudio';

const turn: CompanionTurn = {
  session_id: 'synthetic-session',
  agent_run_id: 'synthetic-run',
  trace_id: 'synthetic-trace',
  context_manifest_id: 'synthetic-context',
  reply_text: '您好。\n\n引用來源：\n- 合成來源',
  reply_language: 'zh-TW',
  result_status: 'SUCCESS',
  safety_decision: 'ALLOW',
  risk_level: 'LOW',
  reason_codes: [],
  session_state: 'COMPLETED',
  transport_status: 'SYNTHESIS_CAPABILITY_ISSUED',
  speech_synthesis_capability: 'synthetic-capability',
  speech_synthesis_expires_at: '2099-01-01T00:00:00Z',
  speech_synthesis_text: '您好。',
  model_route: 'mock',
};
let audio: HTMLAudioElement;
const createUrl = vi.fn();
const revokeUrl = vi.fn();
beforeEach(() => {
  audio = document.createElement('audio');
  vi.spyOn(audio, 'play').mockResolvedValue();
  vi.spyOn(audio, 'pause').mockImplementation(() => undefined);
  vi.stubGlobal(
    'Audio',
    vi.fn(() => audio),
  );
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL = createUrl;
      static revokeObjectURL = revokeUrl;
    },
  );
  createUrl.mockReset().mockReturnValue('blob:synthetic-audio');
  revokeUrl.mockReset();
  mocks.synthesize
    .mockReset()
    .mockResolvedValue({ audioBase64: 'YXVkaW8=', contentType: 'audio/mpeg' });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it('synthesizes only the authorized text once, then stops and replays cached audio', async () => {
  render(createElement(StrictMode, null, createElement(CompanionReplyAudio, { turn })));
  expect(mocks.synthesize).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '播放回覆' }));
  fireEvent.click(await screen.findByRole('button', { name: '停止播放' }));
  expect(mocks.synthesize).toHaveBeenCalledTimes(1);
  expect(mocks.synthesize).toHaveBeenCalledWith(
    '您好。',
    'zh-TW',
    'synthetic-session',
    'synthetic-run',
    'synthetic-capability',
    'normal',
    expect.any(AbortSignal),
  );
  expect(audio.pause).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole('button', { name: '重新播放' }));
  await waitFor(() => expect(audio.play).toHaveBeenCalledTimes(2));
  expect(mocks.synthesize).toHaveBeenCalledTimes(1);
  act(() => audio.dispatchEvent(new Event('ended')));
  expect(screen.getByRole('button', { name: '重新播放' })).toBeTruthy();
});

it.each([
  { ...turn, transport_status: 'TEXT_ONLY' as const },
  { ...turn, reply_language: 'nan-TW' },
  { ...turn, reply_language: 'hak-TW' },
  { ...turn, speech_synthesis_capability: null },
])('does not synthesize without a supported, authorized reply', (unavailable) => {
  render(createElement(CompanionReplyAudio, { turn: unavailable }));
  expect(screen.queryByRole('button')).toBeNull();
  expect(mocks.synthesize).not.toHaveBeenCalled();
});

it('does not submit an expired capability', () => {
  render(
    createElement(CompanionReplyAudio, {
      turn: { ...turn, speech_synthesis_expires_at: '2000-01-01T00:00:00Z' },
    }),
  );
  fireEvent.click(screen.getByRole('button', { name: '播放回覆' }));
  expect(screen.getByRole('status').textContent).toContain('已超過語音播放時間');
  expect(mocks.synthesize).not.toHaveBeenCalled();
});

it('leaves text usable after a provider failure and never reuses a consumed capability', async () => {
  mocks.synthesize.mockRejectedValue(new Error('private upstream details'));
  render(createElement(CompanionReplyAudio, { turn }));
  fireEvent.click(screen.getByRole('button', { name: '播放回覆' }));
  await screen.findByText('語音暫時無法播放，您仍可閱讀文字回覆。');
  expect((screen.getByRole('button') as HTMLButtonElement).disabled).toBe(true);
  expect(document.body.textContent).not.toContain('private upstream');
  expect(mocks.synthesize).toHaveBeenCalledOnce();
});

it('recovers from browser playback blocking without consuming another capability', async () => {
  vi.mocked(audio.play).mockRejectedValueOnce(new DOMException('blocked', 'NotAllowedError'));
  render(createElement(CompanionReplyAudio, { turn }));
  fireEvent.click(screen.getByRole('button', { name: '播放回覆' }));
  await screen.findByText('語音已準備好，請再按一次「重新播放」。');
  fireEvent.click(screen.getByRole('button', { name: '重新播放' }));
  await waitFor(() => expect(audio.play).toHaveBeenCalledTimes(2));
  expect(mocks.synthesize).toHaveBeenCalledOnce();
});

it('aborts synthesis and ignores late audio after leaving the conversation', async () => {
  let resolve: (value: { audioBase64: string; contentType: string }) => void = () => undefined;
  mocks.synthesize.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const view = render(createElement(CompanionReplyAudio, { turn }));
  fireEvent.click(screen.getByRole('button', { name: '播放回覆' }));
  const signal = mocks.synthesize.mock.calls[0][6] as AbortSignal;
  view.unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => {
    resolve({ audioBase64: 'YXVkaW8=', contentType: 'audio/mpeg' });
  });
  expect(audio.play).not.toHaveBeenCalled();
  expect(createUrl).not.toHaveBeenCalled();
});

it('stops playback and releases the audio when a new elder or turn replaces it', async () => {
  const view = render(createElement(CompanionReplyAudio, { key: 'elder-a:run-a', turn }));
  fireEvent.click(screen.getByRole('button', { name: '播放回覆' }));
  await screen.findByRole('button', { name: '停止播放' });
  view.rerender(createElement(CompanionReplyAudio, { key: 'elder-b:run-b', turn }));
  expect(audio.pause).toHaveBeenCalledOnce();
  expect(revokeUrl).toHaveBeenCalledWith('blob:synthetic-audio');
  expect(screen.getByRole('button', { name: '播放回覆' })).toBeTruthy();
});
