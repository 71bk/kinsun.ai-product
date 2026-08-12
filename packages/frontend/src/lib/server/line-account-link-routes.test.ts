import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET as lineLinkCallback } from '../../app/backend/auth/identities/line/callback/route';
import { POST as confirmLineMerge } from '../../app/backend/auth/identities/line/merge/confirm/route';
import { POST as startLineLink } from '../../app/backend/auth/identities/line/start/route';
import { appSessionCookieName } from './app-session-cookie';
import {
  createPendingLineAccountMerge,
  lineAccountMergeCookieName,
  parsePendingLineAccountMerge,
  serializePendingLineAccountMerge,
} from './line-account-merge';
import {
  createLineAccountLinkTransaction,
  lineAccountLinkCookieName,
  parseLineAccountLinkTransaction,
  serializeLineAccountLinkTransaction,
} from './line-account-link-transaction';

const APP_SESSION = `ks1_${'a'.repeat(43)}`;

function configure(): void {
  vi.stubEnv('NODE_ENV', 'development');
  vi.stubEnv('FRONTEND_ORIGIN', 'http://localhost:3000');
  vi.stubEnv('LINE_DIRECT_OIDC_ENABLED', 'true');
  vi.stubEnv('LINE_LOGIN_CHANNEL_ID', '1234567890');
  vi.stubEnv('LINE_LOGIN_CHANNEL_SECRET', 'synthetic-line-channel-secret');
  vi.stubEnv(
    'LINE_ACCOUNT_LINK_CALLBACK_URL',
    'http://localhost:3000/backend/auth/identities/line/callback',
  );
  vi.stubEnv('LINE_OIDC_TRANSACTION_SECRET', 'synthetic-line-transaction-secret-material-32-bytes');
  vi.stubEnv('LINE_OIDC_HANDOFF_SECRET', 'synthetic-line-handoff-secret-material-32-bytes');
  vi.stubEnv('LINE_CHANNEL_SECRET', 'independent-line-messaging-secret');
  vi.stubEnv('GOOGLE_OIDC_HANDOFF_SECRET', 'independent-google-handoff-secret-32-bytes');
  vi.stubEnv('FAMILY_INVITATION_HMAC_SECRET', 'independent-family-secret-material-32-bytes');
  vi.stubEnv('CORE_API_INTERNAL_URL', 'http://127.0.0.1:8000');
}

function request(
  path: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`, init);
}

function cookieValue(response: Response, name: string): string | undefined {
  const header = response.headers.get('set-cookie') ?? '';
  return new RegExp(`(?:^|, )${name}=([^;]*)`).exec(header)?.[1];
}

function claims(nonce: string) {
  return {
    iss: 'https://access.line.me',
    sub: 'U1234567890abcdef',
    aud: '1234567890',
    exp: Math.floor(Date.now() / 1000) + 300,
    iat: Math.floor(Date.now() / 1000) - 5,
    nonce,
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('App Session LINE account linking', () => {
  it('starts a fresh LINE proof bound to the current App Session', async () => {
    configure();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          data: {
            google_linked: true,
            line_linked: false,
            recently_authenticated: true,
          },
        }),
      ),
    );

    const response = await startLineLink(
      request('/backend/auth/identities/line/start', {
        method: 'POST',
        headers: {
          Cookie: `${appSessionCookieName()}=${APP_SESSION}`,
          Origin: 'http://localhost:3000',
        },
      }),
    );

    expect(response.status).toBe(303);
    const location = new URL(response.headers.get('location') ?? '');
    expect(location.searchParams.get('redirect_uri')).toBe(
      'http://localhost:3000/backend/auth/identities/line/callback',
    );
    const serialized = cookieValue(response, lineAccountLinkCookieName());
    expect(parseLineAccountLinkTransaction(serialized)).not.toBeNull();
    expect(serialized).not.toContain(APP_SESSION);
  });

  it('stores a signed confirmation only when Core reports an empty duplicate actor', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-12T00:00:00Z'));
    const transaction = createLineAccountLinkTransaction(APP_SESSION);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const target = String(input);
        if (target === 'https://api.line.me/oauth2/v2.1/token') {
          return Response.json({
            access_token: 'temporary-line-access-token',
            id_token: 'header.payload.signature',
          });
        }
        if (target === 'https://api.line.me/oauth2/v2.1/verify') {
          return Response.json(claims(transaction.nonce));
        }
        if (target === 'http://127.0.0.1:8000/api/v1/internal/auth/line/link') {
          return Response.json({
            data: {
              status: 'MERGE_REQUIRED',
              merge_token: `km1_${'m'.repeat(43)}`,
              expires_at: '2026-08-12T00:10:00Z',
            },
          });
        }
        if (target === 'https://api.line.me/oauth2/v2.1/revoke') {
          return new Response(null, { status: 200 });
        }
        throw new Error(`Unexpected target: ${target}`);
      }),
    );

    const response = await lineLinkCallback(
      request(
        `/backend/auth/identities/line/callback?code=synthetic-code&state=${transaction.state}`,
        {
          headers: {
            Cookie: `${appSessionCookieName()}=${APP_SESSION}; ${lineAccountLinkCookieName()}=${serializeLineAccountLinkTransaction(transaction)}`,
          },
        },
      ),
    );

    expect(response.headers.get('location')).toBe('/account/sign-in-methods?status=merge_required');
    const pending = parsePendingLineAccountMerge(
      cookieValue(response, lineAccountMergeCookieName()),
    );
    expect(pending?.mergeToken).toBe(`km1_${'m'.repeat(43)}`);
  });

  it('confirms consolidation and replaces the now-revoked App Session', async () => {
    configure();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-12T00:00:00Z'));
    const pending = createPendingLineAccountMerge(`km1_${'m'.repeat(43)}`, '2026-08-12T00:10:00Z');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          data: {
            status: 'MERGED',
            session_token: `ks1_${'z'.repeat(43)}`,
            idle_expires_at: '2026-08-19T00:00:00Z',
            absolute_expires_at: '2026-09-11T00:00:00Z',
          },
        }),
      ),
    );

    const response = await confirmLineMerge(
      request('/backend/auth/identities/line/merge/confirm', {
        method: 'POST',
        headers: {
          Cookie: `${appSessionCookieName()}=${APP_SESSION}; ${lineAccountMergeCookieName()}=${serializePendingLineAccountMerge(pending)}`,
          Origin: 'http://localhost:3000',
        },
      }),
    );

    expect(response.headers.get('location')).toBe('/account/sign-in-methods?status=merged');
    expect(cookieValue(response, appSessionCookieName())).toBe(`ks1_${'z'.repeat(43)}`);
    expect(cookieValue(response, lineAccountMergeCookieName())).toBe('');
  });
});
