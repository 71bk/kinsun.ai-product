import { afterEach, describe, expect, it, vi } from 'vitest';
import { handoffGoogleOidcToCore } from './google-oidc-core-handoff';
import { createGoogleOidcTransaction, type GoogleOidcTransaction } from './google-oidc-transaction';

const handoffSecret = 'synthetic-google-handoff-secret-at-least-32-bytes';
const transactionSecret = 'independent-transaction-secret-at-least-32-bytes';

function configure(): GoogleOidcTransaction {
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
  vi.stubEnv('GOOGLE_OIDC_HANDOFF_SECRET', handoffSecret);
  vi.stubEnv('GOOGLE_OIDC_TRANSACTION_SECRET', transactionSecret);
  return createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Google OIDC BFF-to-Core handoff', () => {
  it('sends only the ID token transaction nonce and intent using the dedicated secret', async () => {
    const transaction = configure();
    const sessionToken = `ks1_${'a'.repeat(43)}`;
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json({
          data: {
            status: 'AUTHENTICATED',
            session_token: sessionToken,
            idle_expires_at: '2026-08-18T00:00:00Z',
            absolute_expires_at: '2026-09-10T00:00:00Z',
          },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await handoffGoogleOidcToCore(
      { idToken: 'header.payload.signature' },
      transaction,
    );

    expect(result).toMatchObject({ status: 'AUTHENTICATED', sessionToken });
    const [target, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/internal/auth/google/handoff');
    expect(init).toMatchObject({ cache: 'no-store', method: 'POST', redirect: 'error' });
    expect(init?.headers).toMatchObject({
      'X-Kinsun-BFF-Authorization': `Bearer ${handoffSecret}`,
    });
    expect(JSON.parse(String(init?.body))).toEqual({
      id_token: 'header.payload.signature',
      expected_nonce: transaction.nonce,
      intent: 'ELDER',
    });
    expect(String(init?.body)).not.toContain(transaction.state);
    expect(String(init?.body)).not.toContain(transaction.codeVerifier);
  });

  it('accepts a bounded pending credential without provider profile data', async () => {
    const transaction = configure();
    const pendingToken = `kp1_${'b'.repeat(43)}`;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (): Promise<Response> =>
        Response.json({
          data: {
            status: 'PENDING',
            pending_token: pendingToken,
            expires_at: '2026-08-11T00:10:00Z',
          },
        }),
      ),
    );

    await expect(
      handoffGoogleOidcToCore({ idToken: 'header.payload.signature' }, transaction),
    ).resolves.toEqual({
      status: 'PENDING',
      pendingToken,
      expiresAt: '2026-08-11T00:10:00Z',
    });
  });

  it('fails closed for unsafe config secret reuse and malformed Core responses', async () => {
    const transaction = configure();
    vi.stubEnv('CORE_API_INTERNAL_URL', 'https://user:password@attacker.example');
    vi.stubGlobal('fetch', vi.fn());
    await expect(
      handoffGoogleOidcToCore({ idToken: 'header.payload.signature' }, transaction),
    ).rejects.toThrow('Core Google handoff failed');

    vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
    vi.stubEnv('GOOGLE_OIDC_HANDOFF_SECRET', transactionSecret);
    await expect(
      handoffGoogleOidcToCore({ idToken: 'header.payload.signature' }, transaction),
    ).rejects.toThrow('Core Google handoff failed');

    vi.stubEnv('GOOGLE_OIDC_HANDOFF_SECRET', handoffSecret);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (): Promise<Response> =>
        Response.json({ data: { status: 'PENDING', pending_token: 'raw-invalid-token' } }),
      ),
    );
    await expect(
      handoffGoogleOidcToCore({ idToken: 'header.payload.signature' }, transaction),
    ).rejects.toThrow('Invalid Core Google handoff response');
  });

  it('logs only bounded rejection status and never credentials', async () => {
    const transaction = configure();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (): Promise<Response> => new Response('restricted body', { status: 401 })),
    );

    await expect(
      handoffGoogleOidcToCore({ idToken: 'restricted.id.token' }, transaction),
    ).rejects.toThrow('Core Google handoff failed');

    expect(errorSpy).toHaveBeenCalledWith('[auth] Core Google handoff rejected {"status":401}');
    const log = JSON.stringify(errorSpy.mock.calls);
    expect(log).not.toContain('restricted.id.token');
    expect(log).not.toContain(handoffSecret);
    expect(log).not.toContain(transaction.nonce);
  });
});
