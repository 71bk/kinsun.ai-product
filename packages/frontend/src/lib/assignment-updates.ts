// Invalidation only: no elder, assignment, note or credential is broadcast or stored.
const channelName = 'kinsun-assignment-updates';
const source = crypto.randomUUID();
export function notifyAssignmentUpdated() {
  window.dispatchEvent(new Event(channelName));
  if (typeof BroadcastChannel === 'undefined') return;
  const channel = new BroadcastChannel(channelName);
  channel.postMessage({ source, kind: 'refresh' });
  channel.close();
}
export function watchAssignmentUpdates(refresh: () => void) {
  window.addEventListener(channelName, refresh);
  const channel =
    typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(channelName);
  if (channel)
    channel.onmessage = (event: MessageEvent) => {
      if (event.data?.kind === 'refresh' && event.data?.source !== source) refresh();
    };
  return () => {
    window.removeEventListener(channelName, refresh);
    channel?.close();
  };
}
