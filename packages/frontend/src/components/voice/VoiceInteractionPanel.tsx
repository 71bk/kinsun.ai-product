'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { RecordingState } from '@elderly-care/shared';
import { blobToBase64, BrowserVoiceRecorder } from '@/lib/voice/recorder';
import { VoiceWebSocketClient, type ServerResponsePayload } from '@/lib/voice/websocket-client';
import { MicPermissionGuide } from './MicPermissionGuide';
import { RecordButton } from './RecordButton';

export interface VoiceInteractionPanelProps {
  wsUrl: string;
  token: string;
  /** Elder hasn't granted recording consent yet — disables the mic entirely (A06.2). */
  consentGranted: boolean;
}

export function VoiceInteractionPanel({ wsUrl, token, consentGranted }: VoiceInteractionPanelProps) {
  const [state, setState] = useState<RecordingState>('idle');
  const [needsMicPermission, setNeedsMicPermission] = useState(false);
  const [displayText, setDisplayText] = useState('');
  const [transcript, setTranscript] = useState('');

  const recorderRef = useRef<BrowserVoiceRecorder | null>(null);
  const wsRef = useRef<VoiceWebSocketClient | null>(null);

  useEffect(() => {
    if (!consentGranted) return;

    const recorder = new BrowserVoiceRecorder();
    const ws = new VoiceWebSocketClient();
    recorderRef.current = recorder;
    wsRef.current = ws;

    ws.onStateChange((s) => setState(s));
    ws.onAudioResponse((payload: ServerResponsePayload) => {
      setState('processing');
      if (payload.transcript) setTranscript(payload.transcript);
      if (payload.response) setDisplayText(payload.response);
      const play = async () => {
        if (payload.audioUrl) {
          await recorder.playAudioFromUrl(payload.audioUrl);
        }
        setState('idle');
      };
      void play();
    });

    ws.connect(wsUrl, token).catch(() => {
      setDisplayText('連線失敗，請稍後再試');
    });

    return () => {
      ws.disconnect();
    };
  }, [wsUrl, token, consentGranted]);

  const handlePress = useCallback(async () => {
    const recorder = recorderRef.current;
    const ws = wsRef.current;
    if (!recorder || !ws) return;

    if (state === 'idle') {
      const granted = recorder.hasMicPermission() || (await recorder.requestMicPermission());
      if (!granted) {
        setNeedsMicPermission(true);
        return;
      }
      setNeedsMicPermission(false);
      setDisplayText('');
      setTranscript('');
      ws.startSession();
      await recorder.startRecording();
      setState('recording');
      return;
    }

    if (state === 'recording') {
      const blob = await recorder.stopRecording();
      setState('processing');
      const audioBase64 = await blobToBase64(blob);
      ws.sendAudio(audioBase64, 'opus', 48000);
      ws.stopSession();
    }
  }, [state]);

  if (!consentGranted) {
    return (
      <p style={{ textAlign: 'center', fontSize: 18, color: '#718096' }}>
        請先完成錄音同意設定，才能開始使用語音功能。
      </p>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24 }}>
      <RecordButton state={state} onPress={handlePress} />
      {needsMicPermission && <MicPermissionGuide onRetry={handlePress} />}
      {transcript && (
        <p style={{ maxWidth: 420, textAlign: 'center', fontSize: 15, color: '#718096' }}>您說：「{transcript}」</p>
      )}
      {displayText && (
        <p style={{ maxWidth: 420, textAlign: 'center', fontSize: 20, lineHeight: 1.6 }}>{displayText}</p>
      )}
    </div>
  );
}
