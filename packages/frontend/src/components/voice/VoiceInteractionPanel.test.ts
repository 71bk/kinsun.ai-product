// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ApiRequestError } from '@/lib/api/client';

const mocks = vi.hoisted(() => ({
  transcribe: vi.fn(),
  speak: vi.fn(),
  confirm: vi.fn(),
  remove: vi.fn(),
  play: vi.fn(),
  dispose: vi.fn(),
}));
vi.mock('@/lib/voice/canonical-voice-turn', () => ({
  transcribeTurn: mocks.transcribe,
  speakTurn: mocks.speak,
  VoiceTurnError: class VoiceTurnError extends Error {},
}));
vi.mock('@/lib/voice/recorder', () => ({
  BrowserVoiceRecorder: class {
    hasMicPermission() {
      return true;
    }
    async startRecording() {}
    async stopRecording() {
      return new Blob(['synthetic audio']);
    }
    playAudioFromUrl = mocks.play;
    dispose = mocks.dispose;
  },
}));
vi.mock('@/lib/api/companion', () => ({ confirmAsrGate: mocks.confirm }));
vi.mock('@/lib/api/memories', () => ({ deleteMemoryAsElder: mocks.remove }));
vi.mock('./dev-preview', () => ({ readDevPreviewState: () => null }));
vi.mock('./CompanionCharacter', () => ({
  CompanionCharacter: ({ message }: { message: string }) => createElement('p', null, message),
}));
import { VoiceInteractionPanel } from './VoiceInteractionPanel';

const apiConfig = { apiBaseUrl: '/backend/core' };
const receipt = { memory_id: 'synthetic-memory', version: 2, content: '請叫我王大爺。' };
const reply = {
  replyText: '好的。',
  audioUrl: null,
  textOnlyByLanguage: false,
  resultStatus: 'SUCCESS',
  safetyDecision: 'ALLOW',
  memoryUpdates: [receipt],
};
const props = { apiConfig, elderId: 'synthetic-elder', consentGranted: true };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.transcribe
    .mockReset()
    .mockResolvedValue({
      sessionId: 'voice-session',
      text: '請叫我王大爺',
      decision: 'CAN_SEND_TO_AGENT',
    });
  mocks.speak.mockReset().mockResolvedValue(reply);
  mocks.confirm.mockReset().mockResolvedValue({ decision: 'CAN_SEND_TO_AGENT' });
  mocks.remove.mockReset().mockResolvedValue({});
  mocks.play.mockReset().mockResolvedValue(undefined);
  vi.stubGlobal('URL', { revokeObjectURL: vi.fn() });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function record() {
  fireEvent.click(screen.getByRole('button', { name: '按一下開始說話' }));
  fireEvent.click(await screen.findByRole('button', { name: '我在聽，說完了按一下結束' }));
}

it('shows only Core receipts and undoes the exact memory version', async () => {
  render(createElement(VoiceInteractionPanel, props));
  await record();
  fireEvent.click(await screen.findByRole('button', { name: '撤銷這筆記憶' }));
  await screen.findByText('已撤銷這筆記憶，新對話不會再使用它。');
  expect(mocks.remove).toHaveBeenCalledWith(apiConfig, props.elderId, {
    memoryId: receipt.memory_id,
    version: 2,
  });
  expect(mocks.speak).toHaveBeenCalledWith(apiConfig, 'voice-session', '請叫我王大爺', 'zh-TW');
});

it('does not invent a receipt when the feature or consent is off', async () => {
  mocks.speak.mockResolvedValue({ ...reply, memoryUpdates: [] });
  render(createElement(VoiceInteractionPanel, props));
  await record();
  await screen.findByText('好的。');
  expect(screen.queryByText('已記住')).toBeNull();
});

it('waits for ASR confirmation before submitting the utterance', async () => {
  mocks.transcribe.mockResolvedValue({
    sessionId: 'voice-session',
    text: '請叫我王大爺',
    decision: 'CONFIRMATION_REQUIRED',
  });
  render(createElement(VoiceInteractionPanel, props));
  await record();
  const confirm = await screen.findByRole('button', { name: '對，就是這樣' });
  expect(mocks.speak).not.toHaveBeenCalled();
  fireEvent.click(confirm);
  await screen.findByText('已記住');
  expect(mocks.confirm).toHaveBeenCalledWith(apiConfig, 'voice-session', 'CONFIRM');
});

it('does not save after rejecting uncertain recognition', async () => {
  mocks.transcribe.mockResolvedValue({
    sessionId: 'voice-session',
    text: '教我王大爺',
    decision: 'CONFIRMATION_REQUIRED',
  });
  render(createElement(VoiceInteractionPanel, props));
  await record();
  fireEvent.click(await screen.findByRole('button', { name: '不對，我再說一次' }));
  await screen.findByRole('button', { name: '按一下開始說話' });
  expect(mocks.speak).not.toHaveBeenCalled();
  expect(screen.queryByText('已記住')).toBeNull();
});

it('retains a saved receipt if audio playback is blocked', async () => {
  mocks.speak.mockResolvedValue({ ...reply, audioUrl: 'blob:synthetic' });
  mocks.play.mockRejectedValue(new Error('synthetic playback block'));
  render(createElement(VoiceInteractionPanel, props));
  await record();
  await screen.findByText('語音暫時無法播放，您仍可閱讀文字回覆。');
  expect(screen.getByText('已記住')).toBeTruthy();
  expect(screen.getByText('好的。')).toBeTruthy();
});

it('keeps a version conflict visible without claiming undo success', async () => {
  mocks.remove.mockRejectedValue(new ApiRequestError(409, 'secret internal detail'));
  render(createElement(VoiceInteractionPanel, props));
  await record();
  fireEvent.click(await screen.findByRole('button', { name: '撤銷這筆記憶' }));
  await screen.findByText('這筆記憶已有更新，請到「我的記憶」查看目前內容後再操作。');
  expect(screen.queryByText('已撤銷這筆記憶，新對話不會再使用它。')).toBeNull();
  expect(document.body.textContent).not.toContain('secret internal detail');
});

it('discards late receipts after elder scope changes', async () => {
  let resolve!: (value: typeof reply) => void;
  mocks.speak.mockReturnValue(
    new Promise<typeof reply>((done) => {
      resolve = done;
    }),
  );
  const view = render(createElement(VoiceInteractionPanel, props));
  await record();
  await waitFor(() => expect(mocks.speak).toHaveBeenCalledOnce());
  view.rerender(createElement(VoiceInteractionPanel, { ...props, elderId: 'another-elder' }));
  await act(async () => {
    resolve(reply);
  });
  expect(screen.queryByText('已記住')).toBeNull();
  expect(screen.queryByText('請叫我王大爺。')).toBeNull();
  expect(mocks.dispose).toHaveBeenCalled();
});
