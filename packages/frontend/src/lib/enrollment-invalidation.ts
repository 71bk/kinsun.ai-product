// Ephemeral IDs only. No storage, credentials, reasons, or care data.
const channelName = 'kinsun-enrollment-changed';
const source = `${Date.now()}-${Math.random()}`;
const listeners = new Set<(elderId: string) => void>();
export function publishEnrollmentChange(elderId: string) {
  for (const listener of listeners) listener(elderId);
  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel(channelName);
    channel.postMessage({ elderId, source });
    channel.close();
  }
}
export function subscribeEnrollmentChange(listener: (elderId: string) => void) {
  listeners.add(listener);
  const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(channelName) : null;
  if (channel) channel.onmessage = (event: MessageEvent<unknown>) => {
    const value = event.data as { elderId?: unknown; source?: unknown } | null;
    if (value?.source !== source && typeof value?.elderId === 'string' && value.elderId.length <= 64) listener(value.elderId);
  };
  return () => { listeners.delete(listener); channel?.close(); };
}
