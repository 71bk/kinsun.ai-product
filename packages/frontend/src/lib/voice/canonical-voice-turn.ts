import type { ApiConfig } from '@/lib/api/client';
import { cancelVoiceSession, issueVoiceTicket, runCompanionTurn } from '@/lib/api/companion';
import { blobToPcm16Base64 } from './recorder';
import {
  canSynthesize,
  LanguageUnavailableError,
  synthesizeSpeech,
  transcribeAudio,
  type SpeechLanguage,
} from './speech-gateway-client';

export interface VoiceTurnTranscription {
  sessionId: string;
  text: string;
  decision: 'CAN_SEND_TO_AGENT' | 'CONFIRMATION_REQUIRED' | 'CANNOT_SEND_TO_AGENT';
  confirmationRequired: boolean;
  expiresAt: string;
}

export interface VoiceTurnReply {
  replyText: string;
  audioUrl: string | null;
  textOnlyByLanguage: boolean;
  resultStatus: string;
  safetyDecision: string;
}

export class VoiceTurnError extends Error {
  constructor(
    public readonly stage: 'transcription' | 'language' | 'session' | 'gate' | 'companion',
    message: string,
  ) {
    super(message);
    this.name = 'VoiceTurnError';
  }
}

export async function transcribeTurn(
  apiConfig: ApiConfig,
  elderId: string,
  audio: Blob,
  language: SpeechLanguage = 'zh-TW',
  signal?: AbortSignal,
): Promise<VoiceTurnTranscription> {
  let pcmBase64: string;
  try {
    pcmBase64 = await blobToPcm16Base64(audio);
  } catch {
    throw new VoiceTurnError('transcription', 'could not decode the recorded audio');
  }

  let issued: Awaited<ReturnType<typeof issueVoiceTicket>>;
  try {
    issued = await issueVoiceTicket(apiConfig, elderId, language);
  } catch {
    throw new VoiceTurnError('session', 'could not issue a trusted voice ticket');
  }

  try {
    if (signal?.aborted) {
      await cancelIssuedSession(apiConfig, issued.voice_session.session_id);
      throw new VoiceTurnError('transcription', 'voice transcription was cancelled');
    }
    const result = await transcribeAudio(
      pcmBase64,
      language,
      issued.voice_session.session_id,
      issued.voice_ticket,
      signal,
    );
    if (signal?.aborted) {
      await cancelIssuedSession(apiConfig, issued.voice_session.session_id);
      throw new VoiceTurnError('transcription', 'voice transcription was cancelled');
    }
    if (result.sessionId !== issued.voice_session.session_id) {
      throw new VoiceTurnError('gate', 'voice gate returned a mismatched session');
    }
    return {
      sessionId: result.sessionId,
      text: result.text,
      decision: result.gateDecision,
      confirmationRequired: result.confirmationRequired,
      expiresAt: result.gateExpiresAt,
    };
  } catch (cause) {
    if (cause instanceof VoiceTurnError) throw cause;
    if (signal?.aborted) {
      await cancelIssuedSession(apiConfig, issued.voice_session.session_id);
      throw new VoiceTurnError('transcription', 'voice transcription was cancelled');
    }
    if (cause instanceof LanguageUnavailableError) {
      throw new VoiceTurnError('language', 'this language is not available yet');
    }
    throw new VoiceTurnError('transcription', 'speech recognition is unavailable');
  }
}

async function cancelIssuedSession(apiConfig: ApiConfig, sessionId: string): Promise<void> {
  try {
    await cancelVoiceSession(apiConfig, sessionId);
  } catch {
    // The server-side evidence TTL still prevents Agent use if cancellation
    // races a gateway failure or Core is temporarily unavailable.
  }
}

export async function speakTurn(
  apiConfig: ApiConfig,
  sessionId: string,
  confirmedText: string,
  language: SpeechLanguage,
): Promise<VoiceTurnReply> {
  let turn: Awaited<ReturnType<typeof runCompanionTurn>>;
  try {
    turn = await runCompanionTurn(apiConfig, sessionId, confirmedText);
  } catch {
    throw new VoiceTurnError('companion', 'the companion service is unavailable');
  }

  const synthesizable = canSynthesize(language);
  let audioUrl: string | null = null;
  if (synthesizable) {
    try {
      const audio = await synthesizeSpeech(turn.reply_text, language);
      audioUrl = audioBase64ToUrl(audio.audioBase64, audio.contentType);
    } catch {
      audioUrl = null;
    }
  }

  return {
    replyText: turn.reply_text,
    audioUrl,
    textOnlyByLanguage: !synthesizable,
    resultStatus: turn.result_status,
    safetyDecision: turn.safety_decision,
  };
}

function audioBase64ToUrl(audioBase64: string, contentType: string): string {
  const binary = atob(audioBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return URL.createObjectURL(new Blob([bytes], { type: contentType }));
}
