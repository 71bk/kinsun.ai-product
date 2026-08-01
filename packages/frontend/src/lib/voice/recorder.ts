import type { RecordingState } from '@elderly-care/shared';

/**
 * VoiceInteractionClient (design.md §前端層) — wraps MediaRecorder for
 * capture and HTMLAudioElement for playback. All browser-only; must only
 * be instantiated inside a 'use client' component.
 */
export class BrowserVoiceRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private state: RecordingState = 'idle';
  private currentAudio: HTMLAudioElement | null = null;

  getRecordingState(): RecordingState {
    return this.state;
  }

  /** Returns false (instead of throwing) on denial so callers can show plain-language guidance (A01.3). */
  async requestMicPermission(): Promise<boolean> {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      return true;
    } catch {
      return false;
    }
  }

  hasMicPermission(): boolean {
    return this.stream !== null;
  }

  async startRecording(): Promise<void> {
    if (!this.stream) {
      const granted = await this.requestMicPermission();
      if (!granted) throw new Error('MIC_PERMISSION_DENIED');
    }
    this.chunks = [];
    this.mediaRecorder = new MediaRecorder(this.stream!, { mimeType: 'audio/webm;codecs=opus' });
    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    };
    this.mediaRecorder.start();
    this.state = 'recording';
  }

  async stopRecording(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.mediaRecorder || this.mediaRecorder.state === 'inactive') {
        this.state = 'processing';
        resolve(new Blob(this.chunks, { type: 'audio/webm' }));
        return;
      }
      this.mediaRecorder.onstop = () => {
        this.state = 'processing';
        resolve(new Blob(this.chunks, { type: 'audio/webm' }));
      };
      this.mediaRecorder.stop();
    });
  }

  async playAudioFromUrl(url: string): Promise<void> {
    this.state = 'playing';
    try {
      await new Promise<void>((resolve, reject) => {
        const audio = new Audio(url);
        this.currentAudio = audio;
        audio.onended = () => resolve();
        audio.onerror = () => reject(new Error('AUDIO_PLAYBACK_FAILED'));
        void audio.play().catch(reject);
      });
    } finally {
      this.state = 'idle';
      this.currentAudio = null;
    }
  }

  setState(state: RecordingState): void {
    this.state = state;
  }

  stopPlayback(): void {
    this.currentAudio?.pause();
    this.currentAudio = null;
  }
}

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // Strip the "data:audio/webm;base64," prefix — only the payload goes over the wire.
      resolve(result.slice(result.indexOf(',') + 1));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
