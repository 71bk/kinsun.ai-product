// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HandsFreeRecorder } from './hands-free-recorder';

const stop = vi.fn();
const close = vi.fn(async () => {});
const start = vi.fn();
const recorders: FakeRecorder[] = [];
class FakeRecorder {
  static isTypeSupported() { return true; }
  state = 'inactive';
  mimeType = 'audio/webm';
  onstop = () => {};
  constructor() { recorders.push(this); }
  start() { start(); this.state = 'recording'; }
  stop() { this.state = 'inactive'; this.onstop(); }
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  recorders.length = 0;
  start.mockReset();
  vi.stubGlobal('MediaRecorder', FakeRecorder);
  vi.stubGlobal('AudioContext', class {
    state = 'running';
    resume = async () => {};
    close = close;
    createAnalyser = () => ({ fftSize: 2048, getFloatTimeDomainData: (data: Float32Array) => data.fill(0) });
    createMediaStreamSource = () => ({ connect() {} });
  });
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
    getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop }] })),
  } });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('hands-free recorder resource cleanup', () => {
  it('clears the silence timer when the browser cannot start recording', async () => {
    start.mockImplementation(() => { throw new Error('Synthetic start failure'); });
    const recorder = new HandsFreeRecorder();
    await recorder.open();
    await expect(recorder.capture(new AbortController().signal)).rejects.toThrow('MICROPHONE_UNAVAILABLE');
    expect(vi.getTimerCount()).toBe(0);
    recorder.dispose();
    expect(stop).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledTimes(1);
  });
  it('clears the timer if the browser stops the track unexpectedly', async () => {
    const recorder = new HandsFreeRecorder();
    await recorder.open();
    const recording = recorder.capture(new AbortController().signal);
    recorders[0].stop();
    await expect(recording).resolves.toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    recorder.dispose();
  });
  it('rejects capture and clears the timer on abort', async () => {
    const recorder = new HandsFreeRecorder();
    await recorder.open();
    const controller = new AbortController();
    const recording = recorder.capture(controller.signal);
    controller.abort();
    await expect(recording).rejects.toMatchObject({ name: 'AbortError' });
    expect(vi.getTimerCount()).toBe(0);
    recorder.dispose();
  });
});
