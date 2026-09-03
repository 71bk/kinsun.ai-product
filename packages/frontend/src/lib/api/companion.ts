import { apiFetch, createIdempotencyKey, type ApiConfig } from './client';
import { toVoiceSessionLanguagePreference } from '../voice/language-route';
import type { SpeechLanguage } from '../voice/speech-gateway-client';

export interface VoiceSession {
  session_id: string;
  elder_id: string;
  state:
    | 'CREATED'
    | 'RECORDING'
    | 'AWAITING_CONFIRMATION'
    | 'PROCESSING'
    | 'RESPONDING'
    | 'COMPLETED'
    | 'CANCELLED'
    | 'FAILED';
  language_route: 'ZH_TW' | 'NAN_TW' | 'HAK_TW' | 'EN_US' | 'MIXED' | 'UNKNOWN';
  consent_version: number;
  policy_version: string | null;
  transport_status: 'NOT_CONFIGURED' | 'AVAILABLE';
}

export interface VoiceTicketIssued {
  voice_session: VoiceSession;
  voice_ticket: string;
  expires_at: string;
  transport_status: 'TICKET_ISSUED';
}

export interface AsrGateDecision {
  session_id: string;
  decision: 'CAN_SEND_TO_AGENT' | 'CONFIRMATION_REQUIRED' | 'CANNOT_SEND_TO_AGENT';
  confirmation_required: boolean;
  expires_at: string;
}

export interface CompanionTurn {
  session_id: string;
  agent_run_id: string;
  trace_id: string;
  context_manifest_id: string;
  reply_text: string;
  reply_language: string;
  result_status: 'SUCCESS' | 'BLOCKED' | 'SAFE_FALLBACK' | 'FAILED';
  safety_decision: 'ALLOW' | 'BLOCK' | 'SAFE_FALLBACK' | 'HUMAN_REVIEW';
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  reason_codes: string[];
  session_state: 'COMPLETED';
  transport_status: 'TEXT_ONLY' | 'SYNTHESIS_CAPABILITY_ISSUED';
  speech_synthesis_capability: string | null;
  speech_synthesis_expires_at: string | null;
  speech_synthesis_text: string | null;
  model_route: string;
}

export function createTextSession(config: ApiConfig, elderId: string): Promise<VoiceSession> {
  return apiFetch(config, `/api/v1/elders/${elderId}/voice-sessions`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('text-session') },
    body: JSON.stringify({
      language_preference: 'ZH_TW',
      input_mode: 'text',
      client_timezone: 'Asia/Taipei',
      purpose: 'BASIC_VOICE',
    }),
  });
}

export function issueVoiceTicket(
  config: ApiConfig,
  elderId: string,
  language: SpeechLanguage,
): Promise<VoiceTicketIssued> {
  return apiFetch(config, `/api/v1/elders/${elderId}/voice-tickets`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('voice-ticket') },
    body: JSON.stringify({
      language_preference: toVoiceSessionLanguagePreference(language),
      input_mode: 'voice_with_text_fallback',
      client_audio_format: 'audio/pcm',
      client_timezone: 'Asia/Taipei',
      purpose: 'BASIC_VOICE',
    }),
  });
}

export function confirmAsrGate(
  config: ApiConfig,
  sessionId: string,
  action: 'CONFIRM' | 'REJECT',
): Promise<AsrGateDecision> {
  return apiFetch(config, `/api/v1/voice-sessions/${sessionId}/asr-confirmation`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('asr-confirmation') },
    body: JSON.stringify({ action }),
  });
}

export function cancelVoiceSession(config: ApiConfig, sessionId: string): Promise<VoiceSession> {
  return apiFetch(config, `/api/v1/voice-sessions/${sessionId}/cancel`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('voice-session-cancel') },
  });
}

export function runCompanionTurn(
  config: ApiConfig,
  sessionId: string,
  inputText: string,
): Promise<CompanionTurn> {
  return apiFetch(config, `/api/v1/voice-sessions/${sessionId}/companion-turns`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('companion-turn') },
    body: JSON.stringify({ input_text: inputText }),
  });
}
