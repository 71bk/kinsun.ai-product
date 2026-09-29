import { cancelTabletVoiceTurn, issueTabletVoiceTicket, runTabletVoiceTurn } from '@/lib/api/assisted-elders';
import { blobToPcm16Base64 } from './recorder';
import { audioBase64ToObjectUrl, synthesizeSpeech, transcribeAudio } from './speech-gateway-client';

export type AssistedVoiceResult =
  | { kind: 'retry' }
  | { kind: 'stop' }
  | { kind: 'reply'; text: string; audioUrl: string | null };

export function isStopRequest(text: string): boolean {
  return /^(停止|停止聊天|停止陪伴|不要聊了|結束|結束聊天|stop|stop chatting)[。！!?.\s]*$/i.test(text.trim());
}

export async function runAssistedVoiceTurn(
  audio: Blob, language: 'zh-TW' | 'en-US', signal: AbortSignal,
): Promise<AssistedVoiceResult> {
  const pcm = await blobToPcm16Base64(audio);
  signal.throwIfAborted();
  const issued = await issueTabletVoiceTicket(language, signal);
  const sessionId = issued.voice_session.session_id;
  let completed = false;
  try {
    signal.throwIfAborted();
    const transcription = await transcribeAudio(pcm, language, sessionId, issued.voice_ticket, signal);
    signal.throwIfAborted();
    if (transcription.sessionId !== sessionId || transcription.language !== language) throw new Error('VOICE_SCOPE_MISMATCH');
    if (transcription.gateDecision !== 'CAN_SEND_TO_AGENT' || transcription.confirmationRequired ||
        !transcription.text.trim() || !Number.isFinite(Date.parse(transcription.gateExpiresAt)) ||
        Date.parse(transcription.gateExpiresAt) <= Date.now()) return { kind: 'retry' };
    if (isStopRequest(transcription.text)) return { kind: 'stop' };
    const turn = await runTabletVoiceTurn(sessionId, transcription.text, signal);
    completed = true;
    signal.throwIfAborted();
    if (turn.session_id !== sessionId) throw new Error('VOICE_SCOPE_MISMATCH');
    let audioUrl: string | null = null;
    if (turn.reply_language === language && turn.transport_status === 'SYNTHESIS_CAPABILITY_ISSUED' &&
        turn.speech_synthesis_capability && turn.speech_synthesis_text) {
      try {
        const audio = await synthesizeSpeech(turn.speech_synthesis_text, language, sessionId,
          turn.agent_run_id, turn.speech_synthesis_capability, 'slow', signal);
        signal.throwIfAborted();
        audioUrl = audioBase64ToObjectUrl(audio.audioBase64, audio.contentType);
      } catch { signal.throwIfAborted(); }
    }
    return { kind: 'reply', text: turn.reply_text, audioUrl };
  } finally {
    if (!completed) await cancelTabletVoiceTurn(sessionId).catch(() => undefined);
  }
}
