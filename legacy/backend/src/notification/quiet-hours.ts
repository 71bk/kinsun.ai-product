function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

/**
 * Quiet hours can wrap past midnight (e.g. 22:00-07:00), so this can't be a
 * simple start<=now<=end comparison — when start > end, the "inside" range
 * is actually two segments of the day.
 */
export function isWithinQuietHours(now: Date, quietHoursStart: string, quietHoursEnd: string): boolean {
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  const start = toMinutes(quietHoursStart);
  const end = toMinutes(quietHoursEnd);

  if (start === end) return false; // zero-length quiet window
  if (start < end) {
    return nowMinutes >= start && nowMinutes < end;
  }
  // Wraps past midnight, e.g. 22:00 -> 07:00
  return nowMinutes >= start || nowMinutes < end;
}
