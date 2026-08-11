import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buildGoogleOidcAuthorizationUrl,
  exchangeGoogleOidcAuthorizationCode,
  getGoogleOidcBffConfig,
} from './google-oidc';
import { GoogleOidcCallbackError, validateGoogleOidcCallback } from './google-oidc-callback';
import {
  createGoogleOidcTransaction,
  googleOidcStateMatches,
  googleOidcTransactionCookieName,
  googleOidcTransactionCookieOptions,
  parseGoogleOidcTransaction,
  serializeGoogleOidcTransaction,
} from './google-oidc-transaction';

const clientId = 'synthetic-google-web-client.apps.googleusercontent.com';
const clientSecret = 'synthetic-google-client-secret-at-least-32-bytes';
const transactionSecret = 'synthetic-google-transaction-secret-at-least-32-bytes';

function configureGoogleOidc(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('GOOGLE_OIDC_CLIENT_ID', clientId);
  vi.stubEnv('GOOGLE_OIDC_CLIENT_SECRET', clientSecret);
  vi.stubEnv('GOOGLE_OIDC_TRANSACTION_SECRET', transactionSecret);
  vi.stubEnv('COGNITO_OAUTH_TRANSACTION_SECRET', 'independent-cognito-secret-at-least-32-bytes');
  vi.stubEnv('LINE_LOGIN_LINK_TRANSACTION_SECRET', 'independent-line-secret-at-least-32-bytes');
}

function idToken(nonce: string, claims: Record<string, unknown> = {}): string {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ nonce, ...claims })).toString('base64url');
  return `${header}.${payload}.synthetic-signature`;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('direct Google OIDC BFF transaction', () => {
  it('round-trips only a bounded signed short-lived transaction', () => {
    configureGoogleOidc();
    const transaction = createGoogleOidcTransaction(
      '/onboarding/resolve',
      'FAMILY',
      'family-invite-code',
    );
    const serialized = serializeGoogleOidcTransaction(transaction);

    expect(parseGoogleOidcTransaction(serialized)).toEqual(transaction);
    expect(parseGoogleOidcTransaction(`${serialized}tampered`)).toBeNull();
    expect(googleOidcStateMatches(transaction, transaction.state)).toBe(true);
    expect(googleOidcStateMatches(transaction, 'attacker-state')).toBe(false);
    expect(transaction.codeVerifier).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(transaction.state).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(transaction.nonce).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it('expires the transaction and rejects unsafe onboarding input', () => {
    configureGoogleOidc();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-11T00:00:00Z'));
    const serialized = serializeGoogleOidcTransaction(
      createGoogleOidcTransaction('/onboarding/resolve', 'ELDER'),
    );

    vi.advanceTimersByTime(10 * 60 * 1000 + 1);

    expect(parseGoogleOidcTransaction(serialized)).toBeNull();
    expect(() => createGoogleOidcTransaction('https://attacker.example', 'ELDER')).toThrow(
      'Invalid Google OIDC transaction input',
    );
    expect(() =>
      createGoogleOidcTransaction('/onboarding/resolve', 'ELDER', 'family-invite-code'),
    ).toThrow('Invalid Google OIDC transaction input');
  });

  it('uses an isolated host-only production cookie and signing secret', () => {
    configureGoogleOidc();
    vi.stubEnv('NODE_ENV', 'production');

    expect(googleOidcTransactionCookieName()).toBe('__Host-kinsun_google_oidc_transaction');
    expect(googleOidcTransactionCookieOptions()).toMatchObject({
      httpOnly: true,
      maxAge: 600,
      path: '/',
      sameSite: 'lax',
      secure: true,
    });

    vi.stubEnv('GOOGLE_OIDC_TRANSACTION_SECRET', clientSecret);
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    expect(() => serializeGoogleOidcTransaction(transaction)).toThrow('must be independent');
  });
});

describe('direct Google OIDC authorization request', () => {
  it('uses fixed Google endpoints, a fixed same-origin callback, PKCE, state, and nonce', () => {
    configureGoogleOidc();
    vi.stubEnv('GOOGLE_OIDC_CALLBACK_URL', 'https://attacker.example/callback');
    const config = getGoogleOidcBffConfig();
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const target = buildGoogleOidcAuthorizationUrl(config, transaction);

    expect(config.callbackUrl.toString()).toBe(
      'http://localhost:3000/backend/auth/google/callback',
    );
    expect(target.origin).toBe('https://accounts.google.com');
    expect(target.pathname).toBe('/o/oauth2/v2/auth');
    expect(target.searchParams.get('client_id')).toBe(clientId);
    expect(target.searchParams.get('redirect_uri')).toBe(config.callbackUrl.toString());
    expect(target.searchParams.get('response_type')).toBe('code');
    expect(target.searchParams.get('scope')).toBe('openid email profile');
    expect(target.searchParams.get('code_challenge_method')).toBe('S256');
    expect(target.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(target.searchParams.get('state')).toBe(transaction.state);
    expect(target.searchParams.get('nonce')).toBe(transaction.nonce);
    expect(target.searchParams.get('prompt')).toBe('select_account');
    expect(target.searchParams.has('code_verifier')).toBe(false);
    expect(target.searchParams.has('client_secret')).toBe(false);
  });

  it('fails closed for invalid credentials, origins, and secret reuse', () => {
    configureGoogleOidc();
    vi.stubEnv('GOOGLE_OIDC_CLIENT_ID', '');
    expect(() => getGoogleOidcBffConfig()).toThrow('Google client ID is unavailable');

    vi.stubEnv('GOOGLE_OIDC_CLIENT_ID', clientId);
    vi.stubEnv('FRONTEND_ORIGIN', 'https://frontend.example/path');
    expect(() => getGoogleOidcBffConfig()).toThrow('FRONTEND_ORIGIN is invalid');

    vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
    vi.stubEnv('NODE_ENV', 'production');
    expect(() => getGoogleOidcBffConfig()).toThrow('must use HTTPS');

    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('GOOGLE_OIDC_TRANSACTION_SECRET', clientSecret);
    expect(() => getGoogleOidcBffConfig()).toThrow('must be independent');
  });
});

describe('direct Google OIDC callback envelope', () => {
  it('requires the fixed Google issuer, one code, one state, and the signed transaction', () => {
    configureGoogleOidc();
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const serialized = serializeGoogleOidcTransaction(transaction);
    const params = new URLSearchParams({
      code: 'synthetic-authorization-code',
      iss: 'https://accounts.google.com',
      state: transaction.state,
    });

    expect(validateGoogleOidcCallback(params, serialized)).toEqual({
      authorizationCode: 'synthetic-authorization-code',
      transaction,
    });
  });

  it('returns only bounded failure metadata and preserves a newer transaction', () => {
    configureGoogleOidc();
    const staleTransaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const currentTransaction = createGoogleOidcTransaction('/onboarding/resolve', 'FAMILY');
    const sensitiveValues = new URLSearchParams({
      code: 'restricted-authorization-code',
      error: 'attacker-controlled-error',
      error_description: 'restricted-provider-description',
      iss: 'https://attacker.example',
      state: staleTransaction.state,
    });

    let rejection: unknown;
    try {
      validateGoogleOidcCallback(
        sensitiveValues,
        serializeGoogleOidcTransaction(currentTransaction),
      );
    } catch (error) {
      rejection = error;
    }

    expect(rejection).toBeInstanceOf(GoogleOidcCallbackError);
    expect(rejection).toMatchObject({
      clearCurrentTransaction: false,
      reason: 'PROVIDER_ERROR',
    });
    const serializedError = JSON.stringify(rejection);
    expect(serializedError).not.toContain('restricted-authorization-code');
    expect(serializedError).not.toContain('attacker-controlled-error');
    expect(serializedError).not.toContain('restricted-provider-description');
    expect(serializedError).not.toContain(staleTransaction.state);
  });

  it('fails closed for a missing or mismatched issuer and duplicated parameters', () => {
    configureGoogleOidc();
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const cookie = serializeGoogleOidcTransaction(transaction);
    const base = {
      code: 'synthetic-authorization-code',
      state: transaction.state,
    };

    expect(() => validateGoogleOidcCallback(new URLSearchParams(base), cookie)).toThrowError(
      expect.objectContaining({ reason: 'MALFORMED_REDIRECT' }),
    );
    expect(() =>
      validateGoogleOidcCallback(
        new URLSearchParams({ ...base, iss: 'https://attacker.example' }),
        cookie,
      ),
    ).toThrowError(expect.objectContaining({ reason: 'ISSUER' }));
    const duplicated = new URLSearchParams({
      ...base,
      iss: 'https://accounts.google.com',
    });
    duplicated.append('code', 'second-code');
    expect(() => validateGoogleOidcCallback(duplicated, cookie)).toThrowError(
      expect.objectContaining({ reason: 'MALFORMED_REDIRECT' }),
    );
  });
});

describe('direct Google OIDC authorization-code exchange', () => {
  it('posts the verifier and BFF-only secret but returns only the nonce-correlated ID token', async () => {
    configureGoogleOidc();
    const config = getGoogleOidcBffConfig();
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const syntheticIdToken = idToken(transaction.nonce);
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json({
          access_token: 'discarded-google-access-token',
          expires_in: 3600,
          id_token: syntheticIdToken,
          refresh_token: 'discarded-google-refresh-token',
          token_type: 'Bearer',
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await exchangeGoogleOidcAuthorizationCode(
      config,
      'synthetic-authorization-code',
      transaction,
    );

    expect(result).toEqual({ idToken: syntheticIdToken });
    expect(result).not.toHaveProperty('accessToken');
    expect(result).not.toHaveProperty('refreshToken');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [target, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(target)).toBe('https://oauth2.googleapis.com/token');
    expect(init).toMatchObject({
      cache: 'no-store',
      method: 'POST',
      redirect: 'error',
    });
    const body = new URLSearchParams(String(init?.body));
    expect(body.get('client_id')).toBe(clientId);
    expect(body.get('client_secret')).toBe(clientSecret);
    expect(body.get('code')).toBe('synthetic-authorization-code');
    expect(body.get('code_verifier')).toBe(transaction.codeVerifier);
    expect(body.get('grant_type')).toBe('authorization_code');
    expect(body.get('redirect_uri')).toBe(config.callbackUrl.toString());
  });

  it('rejects a nonce mismatch without logging provider values or tokens', async () => {
    configureGoogleOidc();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const syntheticIdToken = idToken('attacker-controlled-nonce');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (): Promise<Response> => Response.json({ id_token: syntheticIdToken })),
    );

    await expect(
      exchangeGoogleOidcAuthorizationCode(
        getGoogleOidcBffConfig(),
        'synthetic-authorization-code',
        transaction,
      ),
    ).rejects.toThrow('Invalid Google token response');

    expect(errorSpy).toHaveBeenCalledWith(
      '[auth] Google token response validation failed {"id_token_valid":true,"nonce_present":true,"nonce_matches":false}',
    );
    const serializedLog = JSON.stringify(errorSpy.mock.calls);
    expect(serializedLog).not.toContain(syntheticIdToken);
    expect(serializedLog).not.toContain('attacker-controlled-nonce');
    expect(serializedLog).not.toContain(transaction.nonce);
  });

  it('bounds provider and network diagnostics without reading provider error text', async () => {
    configureGoogleOidc();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const fetchMock = vi
      .fn(async (): Promise<Response> => Response.json({}))
      .mockResolvedValueOnce(
        Response.json(
          { error: 'invalid_grant', error_description: 'restricted-provider-detail' },
          { status: 400 },
        ),
      )
      .mockRejectedValueOnce(
        Object.assign(new Error('restricted-network-detail'), {
          name: 'AttackerControlledErrorName',
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      exchangeGoogleOidcAuthorizationCode(
        getGoogleOidcBffConfig(),
        'first-authorization-code',
        transaction,
      ),
    ).rejects.toThrow('Google token exchange failed');
    await expect(
      exchangeGoogleOidcAuthorizationCode(
        getGoogleOidcBffConfig(),
        'second-authorization-code',
        transaction,
      ),
    ).rejects.toThrow('Google token exchange failed');

    expect(errorSpy).toHaveBeenNthCalledWith(
      1,
      '[auth] Google token exchange rejected {"status":400}',
    );
    expect(errorSpy).toHaveBeenNthCalledWith(
      2,
      '[auth] Google token exchange request failed {"error_type":"UnknownError"}',
    );
    const serializedLog = JSON.stringify(errorSpy.mock.calls);
    expect(serializedLog).not.toContain('restricted-provider-detail');
    expect(serializedLog).not.toContain('restricted-network-detail');
    expect(serializedLog).not.toContain('AttackerControlledErrorName');
    expect(serializedLog).not.toContain('first-authorization-code');
    expect(serializedLog).not.toContain('second-authorization-code');
  });

  it('rejects malformed codes and oversized token responses', async () => {
    configureGoogleOidc();
    const transaction = createGoogleOidcTransaction('/onboarding/resolve', 'ELDER');
    const fetchMock = vi.fn(async (): Promise<Response> => new Response('x'.repeat(65_537)));
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      exchangeGoogleOidcAuthorizationCode(getGoogleOidcBffConfig(), 'bad code', transaction),
    ).rejects.toThrow('Invalid Google authorization code');
    expect(fetchMock).not.toHaveBeenCalled();

    await expect(
      exchangeGoogleOidcAuthorizationCode(
        getGoogleOidcBffConfig(),
        'synthetic-authorization-code',
        transaction,
      ),
    ).rejects.toThrow('Invalid Google token response');
  });
});
