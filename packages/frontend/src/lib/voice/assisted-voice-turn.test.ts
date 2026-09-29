import { beforeEach, describe, expect, it, vi } from 'vitest';
import { isStopRequest, runAssistedVoiceTurn } from './assisted-voice-turn';
const api = vi.hoisted(() => ({ cancelTabletVoiceTurn: vi.fn(), issueTabletVoiceTicket: vi.fn(), runTabletVoiceTurn: vi.fn() }));
const speech = vi.hoisted(() => ({ audioBase64ToObjectUrl: vi.fn(), synthesizeSpeech: vi.fn(), transcribeAudio: vi.fn() }));
vi.mock('@/lib/api/assisted-elders', () => api);
vi.mock('./speech-gateway-client', () => speech);
vi.mock('./recorder', () => ({ blobToPcm16Base64: vi.fn(async () => 'pcm') }));
beforeEach(() => {
  vi.resetAllMocks();
  api.issueTabletVoiceTicket.mockResolvedValue({ voice_session: { session_id: 'session-a' }, voice_ticket: 'one-use-ticket' });
  api.cancelTabletVoiceTurn.mockResolvedValue(undefined);
  speech.transcribeAudio.mockResolvedValue({ sessionId: 'session-a', language: 'zh-TW', text: '今天想聊聊天',
    gateDecision: 'CAN_SEND_TO_AGENT', confirmationRequired: false, gateExpiresAt: new Date(Date.now() + 60000).toISOString() });
  api.runTabletVoiceTurn.mockResolvedValue({ session_id: 'session-a', agent_run_id: 'run-a', reply_text: '您好', reply_language: 'zh-TW',
    transport_status: 'SYNTHESIS_CAPABILITY_ISSUED', speech_synthesis_capability: 'reply-bound-capability', speech_synthesis_text: '您好' });
  speech.synthesizeSpeech.mockResolvedValue({ audioBase64: 'audio', contentType: 'audio/mpeg' });
  speech.audioBase64ToObjectUrl.mockReturnValue('blob:reply');
});
const audio = new Blob(['synthetic']);
describe('assisted voice boundaries', () => {
  it('passes only trusted ASR text to the bound conversation and uses reply capability for TTS', async () => {
    const signal = new AbortController().signal;
    expect(await runAssistedVoiceTurn(audio, 'zh-TW', signal)).toEqual({ kind: 'reply', text: '您好', audioUrl: 'blob:reply' });
    expect(api.runTabletVoiceTurn).toHaveBeenCalledWith('session-a', '今天想聊聊天', signal);
    expect(speech.synthesizeSpeech).toHaveBeenCalledWith('您好', 'zh-TW', 'session-a', 'run-a', 'reply-bound-capability', 'slow', signal);
  });
  it.each(['CONFIRMATION_REQUIRED', 'CANNOT_SEND_TO_AGENT'])('cancels %s and never submits it as text', async (gateDecision) => {
    speech.transcribeAudio.mockResolvedValue({ sessionId: 'session-a', language: 'zh-TW', text: 'uncertain', gateDecision });
    expect(await runAssistedVoiceTurn(audio, 'zh-TW', new AbortController().signal)).toEqual({ kind: 'retry' });
    expect(api.runTabletVoiceTurn).not.toHaveBeenCalled();
    expect(api.cancelTabletVoiceTurn).toHaveBeenCalledWith('session-a');
  });
  it('rejects a swapped session before the Agent call', async () => {
    speech.transcribeAudio.mockResolvedValue({ sessionId: 'session-b', language: 'zh-TW' });
    await expect(runAssistedVoiceTurn(audio, 'zh-TW', new AbortController().signal)).rejects.toThrow('VOICE_SCOPE_MISMATCH');
    expect(api.runTabletVoiceTurn).not.toHaveBeenCalled();
  });
  it('does not send a spoken stop request to the Agent', async () => {
    const result = await speech.transcribeAudio();
    speech.transcribeAudio.mockResolvedValue({ ...result, text: '停止。' });
    expect(await runAssistedVoiceTurn(audio, 'zh-TW', new AbortController().signal)).toEqual({ kind: 'stop' });
    expect(api.runTabletVoiceTurn).not.toHaveBeenCalled();
  });
  it('preserves the completed reply when TTS fails', async () => {
    speech.synthesizeSpeech.mockRejectedValue(new Error('unavailable'));
    expect(await runAssistedVoiceTurn(audio, 'zh-TW', new AbortController().signal)).toEqual({ kind: 'reply', text: '您好', audioUrl: null });
    expect(api.cancelTabletVoiceTurn).not.toHaveBeenCalled();
  });
  it('cancels the pending conversation on aborted ASR', async () => {
    const controller = new AbortController();
    speech.transcribeAudio.mockImplementation(async () => { controller.abort(); throw new Error('aborted'); });
    await expect(runAssistedVoiceTurn(audio, 'zh-TW', controller.signal)).rejects.toThrow();
    expect(api.cancelTabletVoiceTurn).toHaveBeenCalledWith('session-a');
    expect(api.runTabletVoiceTurn).not.toHaveBeenCalled();
  });
  it('matches an explicit stop, without interpreting discussion about stopping as a command', () => {
    expect(isStopRequest('停止')).toBe(true);
    expect(isStopRequest('Stop chatting.')).toBe(true);
    expect(isStopRequest('我昨天停止去公園了')).toBe(false);
  });
});
