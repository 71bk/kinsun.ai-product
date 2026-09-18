import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiConfig } from './client';
import {
  ROLE_UNIT_TYPES,
  createStaffInvitation,
  invitationFailure,
  listStaffInvitations,
  revokeStaffInvitation,
} from './staff-invitations';

const config: ApiConfig = { apiBaseUrl: '/backend/core' };
const token = `wi1_${'a'.repeat(43)}`;

function success<T>(data: T, status = 200): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: {
        correlation_id: 'synthetic-correlation',
        timestamp: '2026-09-18T00:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status, headers: { 'Content-Type': 'application/json' } },
  );
}

/**
 * A complete ErrorEnvelopeV1. An incomplete one is silently rejected by
 * `isErrorEnvelope` and surfaces as MALFORMED_API_RESPONSE, which would make
 * these tests assert the transport guard rather than the failure mapping.
 */
function failure(status: number, code: string, retryable = false): Response {
  return new Response(
    JSON.stringify({
      error: {
        code,
        message: 'Resource not found',
        correlation_id: 'synthetic-correlation',
        reason_code:
          status === 409 ? 'VERSION_OR_IDEMPOTENCY_CONFLICT' : 'RESOURCE_NOT_FOUND_OR_FORBIDDEN',
        retryable,
        details: null,
      },
    }),
    { status, headers: { 'Content-Type': 'application/json' } },
  );
}

/** A Response body can only be read once, so every call needs its own. */
function respondWith(factory: () => Response) {
  return vi
    .fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>()
    .mockImplementation(() => Promise.resolve(factory()));
}

function coreInvitation(overrides: Record<string, unknown> = {}) {
  return {
    invitation_id: 'synthetic-invitation',
    display_name: 'Synthetic Worker',
    role_code: 'DAYCARE_CARE_WORKER',
    care_unit_id: 'synthetic-unit',
    status: 'ISSUED',
    expires_at: '2026-09-19T00:00:00Z',
    version: 1,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('staff invitation client', () => {
  it('mirrors the role-to-unit rule Core enforces', () => {
    // Keep in step with ROLE_UNITS in staff_invitation_service.py — a drift here
    // shows up to the administrator as an unexplained "not found".
    expect(ROLE_UNIT_TYPES.DAYCARE_CARE_WORKER).toEqual(['DAYCARE_CENTER', 'COMMUNITY_SITE']);
    expect(ROLE_UNIT_TYPES.HOME_CARE_WORKER).toEqual(['HOME_CARE_AGENCY']);
  });

  it('maps the wire shape without leaking snake_case into the UI', async () => {
    vi.stubGlobal('fetch', respondWith(() => success({ items: [coreInvitation()], next_cursor: null })));

    const page = await listStaffInvitations(config);

    expect(page.items).toEqual([
      {
        invitationId: 'synthetic-invitation',
        displayName: 'Synthetic Worker',
        roleCode: 'DAYCARE_CARE_WORKER',
        careUnitId: 'synthetic-unit',
        status: 'ISSUED',
        expiresAt: '2026-09-19T00:00:00Z',
        version: 1,
      },
    ]);
    expect(page.nextCursor).toBeNull();
  });

  it('sends a fresh idempotency key per issue attempt', async () => {
    const fetchMock = respondWith(() => success(coreInvitation({ invitation_token: token }), 201));
    vi.stubGlobal('fetch', fetchMock);

    const input = {
      email: 'synthetic.worker@example.test',
      displayName: 'Synthetic Worker',
      roleCode: 'DAYCARE_CARE_WORKER' as const,
      careUnitId: 'synthetic-unit',
    };
    const first = await createStaffInvitation(config, input);
    await createStaffInvitation(config, input);

    expect(first.invitationToken).toBe(token);
    const keys = fetchMock.mock.calls.map(([, init]) =>
      new Headers(init?.headers).get('Idempotency-Key'),
    );
    expect(keys[0]).toMatch(/^staff-invitation-/);
    // Replaying the key would make Core reject an issue whose link nobody can
    // ever read, so a retry must never reuse one.
    expect(keys[0]).not.toBe(keys[1]);
  });

  it('sends the expected version so a stale row cannot be revoked blindly', async () => {
    const fetchMock = respondWith(() => success(coreInvitation({ status: 'REVOKED', version: 2 })));
    vi.stubGlobal('fetch', fetchMock);

    const revoked = await revokeStaffInvitation(config, 'synthetic-invitation', 1);

    expect(revoked.status).toBe('REVOKED');
    expect(revoked.version).toBe(2);
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(JSON.parse(String(init?.body))).toEqual({ expected_version: 1 });
  });

  it('percent-encodes the invitation id into the revoke path', async () => {
    const fetchMock = respondWith(() => success(coreInvitation({ status: 'REVOKED', version: 2 })));
    vi.stubGlobal('fetch', fetchMock);

    await revokeStaffInvitation(config, 'a/../b', 1);

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      '/backend/core/api/v1/admin/staff-invitations/a%2F..%2Fb/revoke',
    );
  });

  describe('failure mapping', () => {
    it.each([
      [404, 'not_found', 'unavailable'],
      [403, 'forbidden', 'unavailable'],
      [409, 'conflict', 'conflict'],
      [422, 'validation_error', 'unavailable'],
    ])('reduces a %i to %s', async (status, code, expected) => {
      vi.stubGlobal('fetch', respondWith(() => failure(status, code)));

      await expect(listStaffInvitations(config)).rejects.toMatchObject({
        status,
        reasonCode:
          status === 409 ? 'VERSION_OR_IDEMPOTENCY_CONFLICT' : 'RESOURCE_NOT_FOUND_OR_FORBIDDEN',
      });
      const error = await listStaffInvitations(config).catch((caught: unknown) => caught);
      expect(invitationFailure(error)).toBe(expected);
    });

    it('treats a retryable server failure as a network problem', async () => {
      vi.stubGlobal('fetch', respondWith(() => failure(503, 'service_unavailable', true)));

      const error = await listStaffInvitations(config).catch((caught: unknown) => caught);
      expect(invitationFailure(error)).toBe('network');
    });

    it('treats a thrown fetch as a network problem', () => {
      expect(invitationFailure(new TypeError('Failed to fetch'))).toBe('network');
    });
  });
});
