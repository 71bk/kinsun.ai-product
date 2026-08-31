import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/* The real notFound() throws to abort rendering; mirroring that here is what
   lets a test prove the view is never reached, not merely not returned. */
const { notFound } = vi.hoisted(() => ({
  notFound: vi.fn(() => {
    throw new Error('NEXT_NOT_FOUND');
  }),
}));

vi.mock('next/navigation', () => ({ notFound }));

/* Stubbed so the assertions are about the gate, not about the microphone
   recorder and speech-gateway client the real view pulls in. */
vi.mock('./DevSpeechView', () => ({ DevSpeechView: () => null }));

const { default: DevSpeechPage } = await import('./page');

beforeEach(() => {
  notFound.mockClear();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('dev-speech production gate', () => {
  it('404s in production so the page cannot open a microphone there', () => {
    vi.stubEnv('NODE_ENV', 'production');

    expect(() => DevSpeechPage()).toThrow('NEXT_NOT_FOUND');
    expect(notFound).toHaveBeenCalledOnce();
  });

  it('404s on an unexpected NODE_ENV rather than assuming development', () => {
    vi.stubEnv('NODE_ENV', 'staging');

    expect(() => DevSpeechPage()).toThrow('NEXT_NOT_FOUND');
    expect(notFound).toHaveBeenCalledOnce();
  });

  it('renders the wiring check in development', () => {
    vi.stubEnv('NODE_ENV', 'development');

    expect(DevSpeechPage()).toBeTruthy();
    expect(notFound).not.toHaveBeenCalled();
  });
});
