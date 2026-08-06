import type { AuthorizationContext, UserRole } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';

interface EldersMapping {
  elderId: string;
}

/**
 * Resolves which elder_ids a principal may act on, per role:
 * - elder: only themself
 * - caregiver: elders listed under CG#{caregiverId} -> ELDER#{elderId} mappings
 * - family: elders listed under FM#{familyId} -> ELDER#{elderId} mappings
 * - admin: empty list — admin bypasses elder-scoping in validateDataAccess() instead
 *   of enumerating every elder, since the set is unbounded and irrelevant to the check.
 */
export async function resolveAuthorizedElderIds(
  role: UserRole,
  userId: string,
  tenantId: string,
  table: DynamoTable,
): Promise<string[]> {
  switch (role) {
    case 'elder':
      return [userId];
    case 'caregiver': {
      const items = await table.queryByPk<EldersMapping>(Keys.caregiverPk(userId), 'ELDER#');
      return items.map((i) => i.elderId);
    }
    case 'family': {
      const items = await table.queryByPk<EldersMapping>(Keys.familyPk(userId), 'ELDER#');
      return items.map((i) => i.elderId);
    }
    case 'admin':
      return [];
    default:
      return [];
  }
}

export async function buildAuthorizationContext(
  userId: string,
  role: UserRole,
  tenantId: string,
  table: DynamoTable = new DynamoTable(),
): Promise<AuthorizationContext> {
  const authorizedElderIds = await resolveAuthorizedElderIds(role, userId, tenantId, table);
  return { userId, role, authorizedElderIds, tenantId };
}
