import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { AuthorizationContext, UserRole } from '@elderly-care/shared';
import { validateDataAccess } from './permissions.js';

const nonAdminRole = fc.constantFrom<UserRole>('elder', 'caregiver', 'family');
const elderId = fc.stringMatching(/^[a-z0-9]{1,8}$/);

/**
 * Feature: elderly-care-ai-companion, Property 11: Elder-level data isolation.
 * For any data access request (API layer and data layer), the elder_id of
 * returned data must exactly match an elder_id the requester is authorized
 * for. Different elder_ids' data must never mix in a single query result.
 */
describe('Property 11: Elder-level data isolation', () => {
  it('grants access to non-admin roles iff requestedElderId is in authorizedElderIds', () => {
    fc.assert(
      fc.property(
        nonAdminRole,
        fc.array(elderId, { minLength: 0, maxLength: 10 }),
        elderId,
        (role, authorizedElderIds, requestedElderId) => {
          const authContext: AuthorizationContext = {
            userId: 'u1',
            role,
            authorizedElderIds,
            tenantId: 't1',
          };
          const result = validateDataAccess(authContext, requestedElderId);
          expect(result).toBe(authorizedElderIds.includes(requestedElderId));
        },
      ),
      { numRuns: 200 },
    );
  });

  it('never grants access to an elderId absent from authorizedElderIds, across many elders at once', () => {
    fc.assert(
      fc.property(
        nonAdminRole,
        fc.uniqueArray(elderId, { minLength: 1, maxLength: 10 }),
        (role, allElderIds) => {
          const [authorized, ...rest] = allElderIds;
          const authContext: AuthorizationContext = {
            userId: 'u1',
            role,
            authorizedElderIds: [authorized!],
            tenantId: 't1',
          };
          // The single authorized elder must pass...
          expect(validateDataAccess(authContext, authorized!)).toBe(true);
          // ...and every other elder in the same batch must be denied —
          // simulates a query result set that must never mix elders.
          for (const otherElderId of rest) {
            expect(validateDataAccess(authContext, otherElderId)).toBe(false);
          }
        },
      ),
      { numRuns: 200 },
    );
  });

  it('admin bypasses elder scoping for elder-owned resources', () => {
    fc.assert(
      fc.property(elderId, (requestedElderId) => {
        const authContext: AuthorizationContext = {
          userId: 'admin1',
          role: 'admin',
          authorizedElderIds: [],
          tenantId: 't1',
        };
        expect(validateDataAccess(authContext, requestedElderId)).toBe(true);
      }),
      { numRuns: 50 },
    );
  });

  it('denies everyone but admin on admin-only resources, regardless of elder scoping', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<UserRole>('elder', 'caregiver', 'family', 'admin'),
        elderId,
        (role, requestedElderId) => {
          const authContext: AuthorizationContext = {
            userId: 'u1',
            role,
            authorizedElderIds: [requestedElderId], // even if "authorized" for this elder
            tenantId: 't1',
          };
          const result = validateDataAccess(authContext, requestedElderId, 'system_settings');
          expect(result).toBe(role === 'admin');
        },
      ),
      { numRuns: 100 },
    );
  });
});
