import { describe, expect, it } from 'vitest';
import {
  elderSessionCookieMaxAge,
  normalizeElderSession,
} from './elder-session-cookie';

describe('elder session cookie boundary', () => {
  it('accepts only es1 credentials', () => {
    expect(normalizeElderSession(`es1_${'a'.repeat(43)}`)).toBe(`es1_${'a'.repeat(43)}`);
    expect(normalizeElderSession(`ep1_${'a'.repeat(43)}`)).toBeNull();
    expect(normalizeElderSession(`ks1_${'a'.repeat(43)}`)).toBeNull();
  });

  it('uses the earlier idle or absolute expiry', () => {
    const now = Date.now();
    const idle = new Date(now + 120_000).toISOString();
    const absolute = new Date(now + 600_000).toISOString();

    expect(elderSessionCookieMaxAge(idle, absolute)).toBeGreaterThanOrEqual(118);
    expect(elderSessionCookieMaxAge(idle, absolute)).toBeLessThanOrEqual(120);
  });
});
