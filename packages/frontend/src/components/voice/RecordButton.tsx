'use client';

import type { RecordingState } from '@elderly-care/shared';

const LABEL_BY_STATE: Record<RecordingState, string> = {
  idle: '按這裡開始說話',
  recording: '錄音中，再按一次結束',
  processing: '處理中，請稍候',
  playing: '播放中',
};

const COLOR_BY_STATE: Record<RecordingState, string> = {
  idle: '#2b6cb0',
  recording: '#e53e3e',
  processing: '#dd6b20',
  playing: '#38a169',
};

export interface RecordButtonProps {
  state: RecordingState;
  onPress: () => void;
  disabled?: boolean;
}

/** Single large primary action button — the entire "low operational burden" entry point (A01.1). */
export function RecordButton({ state, onPress, disabled }: RecordButtonProps) {
  const color = COLOR_BY_STATE[state];
  const isBusy = state === 'processing' || state === 'playing';

  return (
    <button
      type="button"
      onClick={onPress}
      disabled={disabled || isBusy}
      aria-label={LABEL_BY_STATE[state]}
      style={{
        width: 220,
        height: 220,
        borderRadius: '50%',
        border: 'none',
        background: color,
        color: '#fff',
        fontSize: 24,
        fontWeight: 700,
        cursor: disabled || isBusy ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        boxShadow: state === 'recording' ? `0 0 0 12px ${color}33` : '0 4px 14px rgba(0,0,0,0.15)',
        transition: 'box-shadow 0.3s ease, background 0.3s ease',
        animation: state === 'recording' ? 'elder-care-pulse 1.4s ease-in-out infinite' : undefined,
      }}
    >
      <span style={{ display: 'block', fontSize: 48, marginBottom: 8 }} aria-hidden="true">
        {state === 'idle' && '🎙️'}
        {state === 'recording' && '⏹️'}
        {state === 'processing' && '⏳'}
        {state === 'playing' && '🔊'}
      </span>
      {LABEL_BY_STATE[state]}
      <style>{`
        @keyframes elder-care-pulse {
          0% { box-shadow: 0 0 0 0 ${color}55; }
          70% { box-shadow: 0 0 0 24px ${color}00; }
          100% { box-shadow: 0 0 0 0 ${color}00; }
        }
      `}</style>
    </button>
  );
}
