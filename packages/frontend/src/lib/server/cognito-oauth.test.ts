import { CognitoIdentityProviderClient } from '@aws-sdk/client-cognito-identity-provider';
import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET as callback } from '../../app/backend/auth/callback/route';
import { GET as lineLinkCallback } from '../../app/backend/auth/identities/line/callback/route';
import { POST as lineLinkStart } from '../../app/backend/auth/identities/line/start/route';
import { POST as login } from '../../app/backend/auth/login/route';
import { POST as logout } from '../../app/backend/auth/logout/route';
import {
  createLineLoginLinkTransaction,
  lineLoginLinkCookieName,
} from './line-login-link-transaction';
import { exchangeAndVerifyLineLoginCode, getLineLoginOAuthConfig } from './line-login-oauth';
import { CognitoIdentityError, linkLineLoginIdentity } from './cognito-identities';
import {
  createOAuthTransaction,
  oauthTransactionCookieName,
  parseOAuthTransaction,
  serializeOAuthTransaction,
  strictRelativeReturnTo,
} from './oauth-transaction';

const transactionSecret = 'synthetic-transaction-secret-long-enough';

function request(
  path: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`, init);
}

function configureOAuth(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('COGNITO_OAUTH_DOMAIN', 'https://example.auth.us-west-2.amazoncognito.com');
  vi.stubEnv('COGNITO_WEB_CLIENT_ID', 'web-client-id');
  vi.stubEnv('COGNITO_CALLBACK_URL', 'http://localhost:3000/backend/auth/callback');
  vi.stubEnv('COGNITO_LOGOUT_URL', 'http://localhost:3000/sign-in');
  vi.stubEnv('COGNITO_OAUTH_TRANSACTION_SECRET', transactionSecret);
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
  vi.stubEnv('CORE_ONBOARDING_REDEEM_URL', '');
}

function idToken(nonce: string): string {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ nonce })).toString('base64url');
  return `${header}.${payload}.signature`;
}

function cookieValue(response: Response, name: string): string | undefined {
  const header = response.headers.get('set-cookie') ?? '';
  return new RegExp(`(?:^|, )${name}=([^;]*)`).exec(header)?.[1];
}

function setCookieHeader(response: Response): string {
  return response.headers.get('set-cookie') ?? '';
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Cognito OAuth transaction', () => {
  it('only accepts a strict relative return path', () => {
    expect(strictRelativeReturnTo('/family')).toBe('/family');
    expect(strictRelativeReturnTo('/family?next=https://attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('/family#https://attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('https://attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('//attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('/\\attacker.example')).toBeNull();
    expect(strictRelativeReturnTo('/not-an-approved-login-destination')).toBeNull();
  });

  it('keeps intent and a family invitation only in a signed short-lived transaction', () => {
    configureOAuth();
    const transaction = createOAuthTransaction(
      '/onboarding/resolve',
      'FAMILY',
      'family-invite-code',
    );
    const serialized = serializeOAuthTransaction(transaction);
    expect(parseOAuthTransaction(serialized)).toMatchObject({
      intent: 'FAMILY',
      invitationCode: 'family-invite-code',
      returnTo: '/onboarding/resolve',
    });
    expect(parseOAuthTransaction(`${serialized}tampered`)).toBeNull();
  });
});

describe('Cognito OAuth BFF routes', () => {
  it('starts Google authorization from a same-origin POST with PKCE, state, and nonce', async () => {
    configureOAuth();
    const response = await login(
      request('/backend/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: 'http://localhost:3000',
        },
        body: new URLSearchParams({ intent: 'ELDER', returnTo: '/family' }),
      }),
    );
    expect(response.status).toBe(303);
    const location = new URL(response.headers.get('location') ?? '');
    expect(location.origin).toBe('https://example.auth.us-west-2.amazoncognito.com');
    expect(location.pathname).toBe('/oauth2/authorize');
    expect(location.searchParams.get('identity_provider')).toBe('Google');
    expect(location.searchParams.get('code_challenge_method')).toBe('S256');
    expect(location.searchParams.get('state')).toBeTruthy();
    expect(location.searchParams.get('nonce')).toBeTruthy();
    expect(location.searchParams.get('code_verifier')).toBeNull();
    expect(cookieValue(response, oauthTransactionCookieName())).toBeTruthy();
  });

  it('only accepts a family invitation over a same-origin form POST', async () => {
    configureOAuth();
    const response = await login(
      request('/backend/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: 'http://localhost:3000',
        },
        body: new URLSearchParams({
          intent: 'FAMILY',
          invitationCode: 'family-invite-code',
          returnTo: '/onboarding/resolve',
        }),
      }),
    );
    const stored = parseOAuthTransaction(cookieValue(response, oauthTransactionCookieName()));
    expect(stored).toMatchObject({ intent: 'FAMILY', invitationCode: 'family-invite-code' });
  });

  it('rejects cross-origin OAuth initiation before creating a transaction', async () => {
    configureOAuth();
    const response = await login(
      request('/backend/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: 'https://attacker.example',
        },
        body: new URLSearchParams({ intent: 'ELDER', returnTo: '/onboarding/resolve' }),
      }),
    );

    expect(response.status).toBe(403);
    expect(cookieValue(response, oauthTransactionCookieName())).toBeUndefined();
  });

  it('exchanges a matching callback code without exposing tokens in the redirect', async () => {
    configureOAuth();
    vi.stubEnv('CORE_ONBOARDING_REDEEM_URL', 'http://127.0.0.1:8000/api/v1/onboarding/resolve');
    const transaction = createOAuthTransaction('/family', 'FAMILY');
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json({
          access_token: 'synthetic-access-token',
          expires_in: 3600,
          id_token: idToken(transaction.nonce),
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await callback(
      request(
        `/backend/auth/callback?code=authorization-code&state=${encodeURIComponent(transaction.state)}`,
        {
          headers: {
            Cookie: `${oauthTransactionCookieName()}=${serializeOAuthTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/family');
    expect(response.headers.get('location')).not.toContain('synthetic-access-token');
    expect(response.headers.get('location')).not.toContain('authorization-code');
    expect(cookieValue(response, 'kinsun_access_token')).toBe('synthetic-access-token');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(init?.body)).toContain('code_verifier=');
  });

  it('uses the ID token only for configured server-to-server onboarding redemption', async () => {
    configureOAuth();
    vi.stubEnv('CORE_ONBOARDING_REDEEM_URL', 'http://127.0.0.1:8000/api/v1/onboarding/resolve');
    const transaction = createOAuthTransaction(
      '/onboarding/resolve',
      'FAMILY',
      'family-invite-code',
    );
    const googleFetch = vi
      .fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json({}),
      )
      .mockResolvedValueOnce(
        Response.json({
          access_token: 'synthetic-access-token',
          expires_in: 3600,
          id_token: idToken(transaction.nonce),
        }),
      )
      .mockResolvedValueOnce(Response.json({ data: { status: 'REDEEMED' } }));
    vi.stubGlobal('fetch', googleFetch);

    const response = await callback(
      request(
        `/backend/auth/callback?code=authorization-code&state=${encodeURIComponent(transaction.state)}`,
        {
          headers: {
            Cookie: `${oauthTransactionCookieName()}=${serializeOAuthTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.status).toBe(303);
    expect(googleFetch).toHaveBeenCalledTimes(2);
    const [target, init] = googleFetch.mock.calls[1] ?? [];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/onboarding/resolve');
    expect(new Headers(init?.headers).get('Authorization')).toMatch(/^Bearer .+\..+\..+$/);
    expect(new Headers(init?.headers).get('Idempotency-Key')).toBe(`oauth-${transaction.state}`);
    expect(String(init?.body)).toContain('family-invite-code');
  });

  it('does not send an ID token to a cross-origin onboarding endpoint', async () => {
    configureOAuth();
    vi.stubEnv('CORE_ONBOARDING_REDEEM_URL', 'https://attacker.example/api/v1/onboarding/resolve');
    const transaction = createOAuthTransaction('/onboarding/resolve', 'ELDER');
    const fetchMock = vi.fn(async (): Promise<Response> =>
      Response.json({
        access_token: 'synthetic-access-token',
        expires_in: 3600,
        id_token: idToken(transaction.nonce),
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await callback(
      request(
        `/backend/auth/callback?code=authorization-code&state=${encodeURIComponent(transaction.state)}`,
        {
          headers: {
            Cookie: `${oauthTransactionCookieName()}=${serializeOAuthTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.headers.get('location')).toBe('/sign-in?error=oauth_failed');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(cookieValue(response, 'kinsun_access_token')).toBeUndefined();
  });

  it('clears the local session before redirecting through Cognito logout', () => {
    configureOAuth();
    const response = logout(
      request('/backend/auth/logout', {
        method: 'POST',
        headers: { Origin: 'http://localhost:3000' },
      }),
    );
    expect(response.status).toBe(303);
    const location = new URL(response.headers.get('location') ?? '');
    expect(location.pathname).toBe('/logout');
    expect(cookieValue(response, 'kinsun_access_token')).toBe('');
    expect(cookieValue(response, oauthTransactionCookieName())).toBe('');
    expect(setCookieHeader(response)).toMatch(
      new RegExp(`${oauthTransactionCookieName()}=;.*Max-Age=0`, 'i'),
    );
  });
});

function configureLineLogin(): void {
  configureOAuth();
  vi.stubEnv('LINE_LOGIN_ENABLED', 'true');
  vi.stubEnv('LINE_LOGIN_CHANNEL_ID', '1234567890');
  vi.stubEnv('LINE_LOGIN_CHANNEL_SECRET', 'synthetic-line-login-channel-secret');
  vi.stubEnv(
    'LINE_LOGIN_LINK_CALLBACK_URL',
    'http://localhost:3000/backend/auth/identities/line/callback',
  );
  vi.stubEnv('LINE_LOGIN_LINK_TRANSACTION_SECRET', 'synthetic-line-link-secret-long-enough');
  vi.stubEnv('COGNITO_LINE_PROVIDER_NAME', 'LINE');
  vi.stubEnv('COGNITO_REGION', 'us-west-2');
  vi.stubEnv('COGNITO_USER_POOL_ID', 'us-west-2_synthetic');
}

function googleLinkedUser() {
  return {
    Username: 'Google_synthetic-subject',
    UserAttributes: [
      { Name: 'email', Value: 'person@example.test' },
      { Name: 'email_verified', Value: 'true' },
      {
        Name: 'identities',
        Value: JSON.stringify([{ providerName: 'Google', userId: 'google-subject' }]),
      },
    ],
  };
}

describe('LINE Login Cognito linking', () => {
  it('uses the LINE Hosted UI callback only to require an existing Core Actor', async () => {
    configureLineLogin();
    const transaction = createOAuthTransaction('/family', 'FAMILY', undefined, 'LINE');
    const fetchMock = vi
      .fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
        Response.json({}),
      )
      .mockResolvedValueOnce(
        Response.json({
          access_token: 'synthetic-cognito-access-token',
          expires_in: 3600,
          id_token: idToken(transaction.nonce),
        }),
      )
      .mockResolvedValueOnce(Response.json({ data: { actor_id: 'synthetic' } }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await callback(
      request(
        `/backend/auth/callback?code=line-code&state=${encodeURIComponent(transaction.state)}`,
        {
          headers: {
            Cookie: `${oauthTransactionCookieName()}=${serializeOAuthTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/family');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [target, init] = fetchMock.mock.calls[1] ?? [];
    expect(String(target)).toBe('http://127.0.0.1:8000/api/v1/me');
    expect(init?.method).toBe('GET');
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer synthetic-cognito-access-token',
    );
    expect(init?.body).toBeUndefined();
  });

  it('links the verified LINE subject to the current Google Cognito user and clears the transaction', async () => {
    configureLineLogin();
    let adminLinkInput: unknown = null;
    const sendMock = async (command: unknown): Promise<unknown> => {
      const cognitoCommand = command as {
        constructor: { name: string };
        input?: unknown;
      };
      if (cognitoCommand.constructor.name === 'GetUserCommand') return googleLinkedUser();
      if (cognitoCommand.constructor.name === 'AdminLinkProviderForUserCommand') {
        adminLinkInput = cognitoCommand.input;
        return {};
      }
      throw new Error('Unexpected Cognito command');
    };
    vi.spyOn(CognitoIdentityProviderClient.prototype, 'send').mockImplementation(
      sendMock as CognitoIdentityProviderClient['send'],
    );

    const startResponse = await lineLinkStart(
      request('/backend/auth/identities/line/start', {
        method: 'POST',
        headers: {
          Cookie: 'kinsun_access_token=synthetic-cognito-access-token',
          Origin: 'http://localhost:3000',
        },
      }),
    );
    expect(startResponse.status).toBe(303);
    const lineTransactionCookie = cookieValue(startResponse, lineLoginLinkCookieName());
    expect(lineTransactionCookie).toBeTruthy();
    const authorizationUrl = new URL(startResponse.headers.get('location') ?? '');
    expect(authorizationUrl.searchParams.get('code_challenge_method')).toBe('S256');
    expect(authorizationUrl.searchParams.has('code_verifier')).toBe(false);
    const state = authorizationUrl.searchParams.get('state');
    const nonce = authorizationUrl.searchParams.get('nonce');
    expect(state).toBeTruthy();
    expect(nonce).toBeTruthy();

    const fetchMock = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
      const target = String(input);
      if (target.endsWith('/token')) {
        return Response.json({
          access_token: 'synthetic-line-access-token',
          id_token: 'synthetic-line-id-token',
        });
      }
      if (target.endsWith('/verify')) {
        return Response.json({
          iss: 'https://access.line.me',
          aud: '1234567890',
          nonce,
          exp: Math.floor(Date.now() / 1000) + 300,
          sub: 'U00000000000000000000000000000000',
          email: 'person@example.test',
        });
      }
      if (target.endsWith('/revoke')) return new Response(null, { status: 200 });
      throw new Error('Unexpected LINE request');
    });
    vi.stubGlobal('fetch', fetchMock);

    const callbackResponse = await lineLinkCallback(
      request(
        `/backend/auth/identities/line/callback?code=line-code&state=${encodeURIComponent(
          state ?? '',
        )}`,
        {
          headers: {
            Cookie: `kinsun_access_token=synthetic-cognito-access-token; ${lineLoginLinkCookieName()}=${lineTransactionCookie}`,
          },
        },
      ),
    );

    expect(callbackResponse.status).toBe(303);
    expect(callbackResponse.headers.get('location')).toBe('/account/sign-in-methods?status=linked');
    expect(setCookieHeader(callbackResponse)).toMatch(
      new RegExp(`${lineLoginLinkCookieName()}=;.*Max-Age=0`, 'i'),
    );
    expect(adminLinkInput).toMatchObject({
      UserPoolId: 'us-west-2_synthetic',
      DestinationUser: {
        ProviderName: 'Cognito',
        ProviderAttributeValue: 'Google_synthetic-subject',
      },
      SourceUser: {
        ProviderName: 'LINE',
        ProviderAttributeName: 'Cognito_Subject',
        ProviderAttributeValue: 'U00000000000000000000000000000000',
      },
    });
    expect(fetchMock.mock.calls.map(([target]) => String(target))).toContain(
      'https://api.line.me/oauth2/v2.1/revoke',
    );
  });

  it('revokes the temporary LINE access token when ID token verification fails', async () => {
    configureLineLogin();
    const transaction = createLineLoginLinkTransaction('Google_synthetic-subject');
    const requests: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const target = String(input);
        requests.push(target);
        if (target.endsWith('/token')) {
          return Response.json({
            access_token: 'synthetic-line-access-token',
            id_token: 'synthetic-line-id-token',
          });
        }
        if (target.endsWith('/verify')) return new Response(null, { status: 401 });
        if (target.endsWith('/revoke')) return new Response(null, { status: 200 });
        throw new Error('Unexpected LINE request');
      }),
    );

    await expect(
      exchangeAndVerifyLineLoginCode(
        getLineLoginOAuthConfig(),
        'synthetic-authorization-code',
        transaction,
      ),
    ).rejects.toThrow('LINE ID token verification failed');
    expect(requests.at(-1)).toBe('https://api.line.me/oauth2/v2.1/revoke');
  });

  it('normalizes an AdminLink provider collision to a fail-closed identity conflict', async () => {
    configureLineLogin();
    const sendMock = async (command: unknown): Promise<unknown> => {
      const cognitoCommand = command as { constructor: { name: string } };
      if (cognitoCommand.constructor.name === 'GetUserCommand') return googleLinkedUser();
      const collision = new Error('synthetic collision');
      collision.name = 'AliasExistsException';
      throw collision;
    };
    vi.spyOn(CognitoIdentityProviderClient.prototype, 'send').mockImplementation(
      sendMock as CognitoIdentityProviderClient['send'],
    );

    const operation = linkLineLoginIdentity(
      'synthetic-cognito-access-token',
      {
        subject: 'U00000000000000000000000000000000',
        email: 'person@example.test',
      },
      createLineLoginLinkTransaction('Google_synthetic-subject'),
    );
    await expect(operation).rejects.toBeInstanceOf(CognitoIdentityError);
    await expect(operation).rejects.toMatchObject({ reason: 'IDENTITY_CONFLICT' });
  });
});

describe('LINE Login destination binding', () => {
  it('rejects an A-to-B session switch without storing the raw destination identity', async () => {
    configureLineLogin();
    let getUserCalls = 0;
    let adminLinkAttempted = false;
    const sendMock = async (command: unknown): Promise<unknown> => {
      const cognitoCommand = command as { constructor: { name: string } };
      if (cognitoCommand.constructor.name === 'GetUserCommand') {
        getUserCalls += 1;
        return getUserCalls === 1
          ? googleLinkedUser()
          : { ...googleLinkedUser(), Username: 'Google_switched-account' };
      }
      if (cognitoCommand.constructor.name === 'AdminLinkProviderForUserCommand') {
        adminLinkAttempted = true;
        return {};
      }
      throw new Error('Unexpected Cognito command');
    };
    vi.spyOn(CognitoIdentityProviderClient.prototype, 'send').mockImplementation(
      sendMock as CognitoIdentityProviderClient['send'],
    );

    const startResponse = await lineLinkStart(
      request('/backend/auth/identities/line/start', {
        method: 'POST',
        headers: {
          Cookie: 'kinsun_access_token=account-a-access-token',
          Origin: 'http://localhost:3000',
        },
      }),
    );
    const lineTransactionCookie = cookieValue(startResponse, lineLoginLinkCookieName());
    expect(lineTransactionCookie).toBeTruthy();
    const authorizationUrl = new URL(startResponse.headers.get('location') ?? '');
    const state = authorizationUrl.searchParams.get('state');
    const nonce = authorizationUrl.searchParams.get('nonce');

    const encodedPayload = lineTransactionCookie?.split('.')[0] ?? '';
    const transactionPayload = JSON.parse(
      Buffer.from(encodedPayload, 'base64url').toString('utf8'),
    ) as Record<string, unknown>;
    expect(transactionPayload.destinationFingerprint).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(transactionPayload).not.toHaveProperty('cognitoUsername');
    expect(JSON.stringify(transactionPayload)).not.toContain('Google_synthetic-subject');

    const lineRequests: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const target = String(input);
        lineRequests.push(target);
        if (target.endsWith('/token')) {
          return Response.json({
            access_token: 'synthetic-line-access-token',
            id_token: 'synthetic-line-id-token',
          });
        }
        if (target.endsWith('/verify')) {
          return Response.json({
            iss: 'https://access.line.me',
            aud: '1234567890',
            nonce,
            exp: Math.floor(Date.now() / 1000) + 300,
            sub: 'U00000000000000000000000000000000',
            email: 'person@example.test',
          });
        }
        if (target.endsWith('/revoke')) return new Response(null, { status: 200 });
        throw new Error('Unexpected LINE request');
      }),
    );

    const callbackResponse = await lineLinkCallback(
      request(
        `/backend/auth/identities/line/callback?code=line-code&state=${encodeURIComponent(
          state ?? '',
        )}`,
        {
          headers: {
            Cookie: `kinsun_access_token=account-b-access-token; ${lineLoginLinkCookieName()}=${lineTransactionCookie}`,
          },
        },
      ),
    );

    expect(callbackResponse.status).toBe(303);
    expect(callbackResponse.headers.get('location')).toBe(
      '/account/sign-in-methods?error=link_destination_changed',
    );
    expect(adminLinkAttempted).toBe(false);
    expect(lineRequests.at(-1)).toBe('https://api.line.me/oauth2/v2.1/revoke');
    expect(setCookieHeader(callbackResponse)).toMatch(
      new RegExp(`${lineLoginLinkCookieName()}=;.*Max-Age=0`, 'i'),
    );
  });
});
