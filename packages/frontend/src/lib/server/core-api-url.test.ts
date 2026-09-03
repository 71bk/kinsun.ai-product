import { afterEach, describe, expect, it, vi } from 'vitest';
import { resolveCoreApiBaseUrl } from './core-api-url';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('Core API internal URL', () => {
  it('requires HTTPS for non-loopback Production endpoints', () => {
    vi.stubEnv('NODE_ENV', 'production');

    for (const value of ['http://core.internal:8000', 'http://10.0.0.8:8000']) {
      vi.stubEnv('CORE_API_INTERNAL_URL', value);
      expect(resolveCoreApiBaseUrl()).toBeNull();
    }

    vi.stubEnv('CORE_API_INTERNAL_URL', 'https://core.internal:8443/base');
    expect(resolveCoreApiBaseUrl()?.toString()).toBe('https://core.internal:8443/base/');
  });

  it('allows explicit loopback HTTP endpoints in Production', () => {
    vi.stubEnv('NODE_ENV', 'production');

    for (const value of [
      'http://localhost:8000',
      'http://127.0.0.1:8000',
      'http://127.10.20.30:8000',
      'http://[::1]:8000',
    ]) {
      vi.stubEnv('CORE_API_INTERNAL_URL', value);
      expect(resolveCoreApiBaseUrl()).not.toBeNull();
    }
  });

  it('allows HTTP outside Production but rejects URL credentials and metadata', () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('CORE_API_INTERNAL_URL', 'http://core.internal:8000');
    expect(resolveCoreApiBaseUrl()).not.toBeNull();

    for (const value of [
      'https://user:password@core.internal',
      'https://core.internal?token=secret',
      'https://core.internal#fragment',
      'file:///tmp/core.sock',
    ]) {
      vi.stubEnv('CORE_API_INTERNAL_URL', value);
      expect(resolveCoreApiBaseUrl()).toBeNull();
    }
  });

  it('uses the loopback default only when the caller opts in', () => {
    vi.stubEnv('NODE_ENV', 'production');
    delete process.env.CORE_API_INTERNAL_URL;

    expect(resolveCoreApiBaseUrl()).toBeNull();
    expect(resolveCoreApiBaseUrl({ allowLocalDefault: true })?.toString()).toBe(
      'http://127.0.0.1:8000/',
    );
  });
});
