/** Local silence detection only. ASR and its confidence gate remain in Speech/Core. */
export class HandsFreeRecorder {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private disposed = false;

  async open(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: {
      echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    } });
    if (this.disposed) { stream.getTracks().forEach((track) => track.stop()); throw new Error('CANCELLED'); }
    this.stream = stream;
    this.context = new AudioContext();
    await this.context.resume();
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 2048;
    this.context.createMediaStreamSource(stream).connect(this.analyser);
  }

  capture(signal: AbortSignal): Promise<Blob | null> {
    signal.throwIfAborted();
    if (!this.stream || !this.analyser) throw new Error('MICROPHONE_UNAVAILABLE');
    const type = ['audio/webm;codecs=opus', 'audio/mp4'].find((mime) => MediaRecorder.isTypeSupported(mime));
    const recorder = new MediaRecorder(this.stream, type ? { mimeType: type } : undefined);
    const analyser = this.analyser;
    return new Promise((resolve, reject) => {
      const chunks: Blob[] = [];
      const samples = new Float32Array(analyser.fftSize);
      const started = performance.now();
      let lastSpeech = started;
      let speechFrames = 0;
      let finished = false;
      const cleanup = () => {
        clearInterval(timer);
        signal.removeEventListener('abort', finish);
      };
      const finish = () => {
        if (finished) return;
        finished = true;
        cleanup();
        if (recorder.state !== 'inactive') recorder.stop();
      };
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => { finish(); reject(new Error('MICROPHONE_UNAVAILABLE')); };
      recorder.onstop = () => {
        finished = true;
        cleanup();
        if (signal.aborted) reject(new DOMException('Cancelled', 'AbortError'));
        else resolve(speechFrames >= 3 ? new Blob(chunks, { type: recorder.mimeType }) : null);
      };
      const timer = setInterval(() => {
        analyser.getFloatTimeDomainData(samples);
        const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
        const now = performance.now();
        if (rms > 0.015) { speechFrames += 1; lastSpeech = now; }
        if ((speechFrames >= 3 && now - lastSpeech >= 1400) || now - started >= 15_000) finish();
      }, 100);
      signal.addEventListener('abort', finish, { once: true });
      try { recorder.start(); }
      catch { cleanup(); reject(new Error('MICROPHONE_UNAVAILABLE')); }
    });
  }

  dispose(): void {
    this.disposed = true;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    if (this.context && this.context.state !== 'closed') void this.context.close();
  }
}
