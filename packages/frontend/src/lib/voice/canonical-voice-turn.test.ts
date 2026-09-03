import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  blobToPcm16Base64: vi.fn(),
  cancelVoiceSession: vi.fn(),
  canSynthesize: vi.fn(),
  issueVoiceTicket: vi.fn(),
  runCompanionTurn: vi.fn(),
  synthesizeSpeech: vi.fn(),
  transcribeAudio: vi.fn(),
}));

vi.mock('@/lib/api/companion', () => ({
  cancelVoiceSession: mocks.cancelVoiceSession,
  issueVoiceTicket: mocks.issueVoiceTicket,
  runCompanionTurn: mocks.runCompanionTurn,
}));

vi.mock('./recorder', () => ({
  blobToPcm16Base64: mocks.blobToPcm16Base64,
}));

vi.mock('./speech-gateway-client', () => ({
  canSynthesize: mocks.canSynthesize,
  LanguageUnavailableError: class LanguageUnavailableError extends Error {},
  synthesizeSpeech: mocks.synthesizeSpeech,
  transcribeAudio: mocks.transcribeAudio,
}));

import { speakTurn, transcribeTurn } from './canonical-voice-turn';

const config = { apiBaseUrl: '/backend/core' };

beforeEach(() => {
  mocks.blobToPcm16Base64.mockReset().mockResolvedValue('pcm-base64');
  mocks.cancelVoiceSession.mockReset().mockResolvedValue({ state: 'CANCELLED' });
  mocks.canSynthesize
    .mockReset()
    .mockImplementation((language: string) => language === 'zh-TW' || language === 'en-US');
  mocks.issueVoiceTicket.mockReset().mockResolvedValue({
    voice_session: { session_id: 'session-1' },
    voice_ticket: 'opaque-ticket',
  });
  mocks.transcribeAudio.mockReset().mockResolvedValue({
    sessionId: 'session-1',
    text: '可信的合成逐字稿',
    gateDecision: 'CONFIRMATION_REQUIRED',
    confirmationRequired: true,
    gateExpiresAt: '2026-08-10T12:00:00Z',
  });
  mocks.runCompanionTurn.mockReset().mockResolvedValue({
    session_id: 'session-1',
    agent_run_id: 'agent-run-1',
    reply_text: '安全的合成回覆',
    reply_language: 'zh-TW',
    speech_synthesis_text: '安全的合成回覆',
    speech_synthesis_capability: 'synthesis-capability',
    transport_status: 'SYNTHESIS_CAPABILITY_ISSUED',
    result_status: 'SUCCESS',
    safety_decision: 'ALLOW',
  });
  mocks.synthesizeSpeech.mockReset().mockResolvedValue({
    audioBase64: '',
    contentType: 'audio/mpeg',
  });
});

describe('canonical voice turn', () => {
  it('binds browser audio to a Core-issued ticket and trusted gate decision', async () => {
    const result = await transcribeTurn(config, 'elder-1', new Blob(['audio']), 'en-US');

    expect(mocks.issueVoiceTicket).toHaveBeenCalledWith(config, 'elder-1', 'en-US');
    expect(mocks.transcribeAudio).toHaveBeenCalledWith(
      'pcm-base64',
      'en-US',
      'session-1',
      'opaque-ticket',
      undefined,
    );
    expect(result).toMatchObject({
      sessionId: 'session-1',
      decision: 'CONFIRMATION_REQUIRED',
      confirmationRequired: true,
    });
  });

  it('runs Agent on the already gated session rather than creating a new one', async () => {
    const objectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:synthetic-audio');

    await speakTurn(config, 'session-1', 'confirmed transcript', 'zh-TW');

    expect(mocks.runCompanionTurn).toHaveBeenCalledWith(
      config,
      'session-1',
      'confirmed transcript',
    );
    expect(mocks.synthesizeSpeech).toHaveBeenCalledWith(
      '安全的合成回覆',
      'zh-TW',
      'session-1',
      'agent-run-1',
      'synthesis-capability',
    );
    objectUrl.mockRestore();
  });

  it('keeps citations on screen but excludes them from synthesized speech', async () => {
    const replyText = '回答內容\n\n引用來源：\n- [國民健康署《手冊》](https://example.test/guide)';
    mocks.runCompanionTurn.mockResolvedValueOnce({
      session_id: 'session-1',
      agent_run_id: 'agent-run-1',
      reply_text: replyText,
      reply_language: 'zh-TW',
      speech_synthesis_text: '回答內容',
      speech_synthesis_capability: 'synthesis-capability',
      transport_status: 'SYNTHESIS_CAPABILITY_ISSUED',
      result_status: 'SUCCESS',
      safety_decision: 'ALLOW',
    });
    const objectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:synthetic-audio');

    const reply = await speakTurn(config, 'session-1', 'confirmed transcript', 'zh-TW');

    expect(mocks.synthesizeSpeech).toHaveBeenCalledWith(
      '回答內容',
      'zh-TW',
      'session-1',
      'agent-run-1',
      'synthesis-capability',
    );
    expect(reply.replyText).toBe(replyText);
    objectUrl.mockRestore();
  });

  it('does not send a language that differs from the Core-bound reply language', async () => {
    mocks.runCompanionTurn.mockResolvedValueOnce({
      session_id: 'session-1',
      agent_run_id: 'agent-run-1',
      reply_text: 'Authorized English reply',
      reply_language: 'en-US',
      speech_synthesis_text: 'Authorized English reply',
      speech_synthesis_capability: 'synthesis-capability',
      transport_status: 'SYNTHESIS_CAPABILITY_ISSUED',
      result_status: 'SUCCESS',
      safety_decision: 'ALLOW',
    });

    const reply = await speakTurn(config, 'session-1', 'confirmed transcript', 'zh-TW');

    expect(mocks.synthesizeSpeech).not.toHaveBeenCalled();
    expect(reply).toMatchObject({ audioUrl: null, textOnlyByLanguage: true });
  });

  it('cancels the Core session when ASR is aborted after ticket issuance', async () => {
    const controller = new AbortController();
    mocks.transcribeAudio.mockImplementationOnce(async () => {
      controller.abort();
      throw new Error('browser request aborted');
    });

    await expect(
      transcribeTurn(config, 'elder-1', new Blob(['audio']), 'zh-TW', controller.signal),
    ).rejects.toMatchObject({ stage: 'transcription' });

    expect(mocks.cancelVoiceSession).toHaveBeenCalledWith(config, 'session-1');
    expect(mocks.runCompanionTurn).not.toHaveBeenCalled();
  });

  it.each(['nan-TW', 'hak-TW'] as const)(
    'keeps %s replies text-only without requesting TTS',
    async (language) => {
      const reply = await speakTurn(config, 'session-1', 'confirmed transcript', language);

      expect(mocks.synthesizeSpeech).not.toHaveBeenCalled();
      expect(reply).toMatchObject({ audioUrl: null, textOnlyByLanguage: true });
    },
  );
});
