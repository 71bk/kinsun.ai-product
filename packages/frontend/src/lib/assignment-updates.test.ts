// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { notifyAssignmentUpdated, watchAssignmentUpdates } from './assignment-updates';

afterEach(() => {
  vi.unstubAllGlobals();
});
it('invalidates local listeners once, ignores its own broadcast, and accepts other tabs', () => {
  const channels: {
    onmessage?: (event: { data: unknown }) => void;
    close: ReturnType<typeof vi.fn>;
  }[] = [];
  class Channel {
    onmessage?: (event: { data: unknown }) => void;
    close = vi.fn();
    constructor() {
      channels.push(this);
    }
    postMessage(data: unknown) {
      for (const channel of channels) if (channel !== this) channel.onmessage?.({ data });
    }
  }
  vi.stubGlobal('BroadcastChannel', Channel);
  const refresh = vi.fn();
  const stop = watchAssignmentUpdates(refresh);
  notifyAssignmentUpdated();
  expect(refresh).toHaveBeenCalledTimes(1);
  channels[0].onmessage?.({ data: { source: 'other-tab', kind: 'refresh' } });
  expect(refresh).toHaveBeenCalledTimes(2);
  channels[0].onmessage?.({ data: { source: 'other-tab', kind: 'unrelated' } });
  expect(refresh).toHaveBeenCalledTimes(2);
  stop();
  expect(channels[0].close).toHaveBeenCalledOnce();
});
