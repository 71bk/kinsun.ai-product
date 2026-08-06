import type { AuthorizationContext, UserRole } from '@elderly-care/shared';

/**
 * Resources and actions mirror the role permission matrix in design.md
 * §角色權限矩陣. `own` resources are scoped to authContext.authorizedElderIds;
 * `admin` resources (knowledge base, system settings) are never elder-scoped.
 */
export type Resource =
  | 'conversation'
  | 'event'
  | 'memory'
  | 'summary'
  | 'persona'
  | 'knowledge_base'
  | 'system_settings';

export type Action = 'read' | 'write' | 'confirm' | 'delete' | 'publish';

type PermissionMatrix = Record<UserRole, Partial<Record<Resource, readonly Action[]>>>;

/** Role x Resource -> allowed actions. An absent resource key means no access. */
export const PERMISSION_MATRIX: PermissionMatrix = {
  elder: {
    conversation: ['read'],
    event: ['read'],
    memory: ['read', 'confirm', 'delete'],
    summary: ['read'],
  },
  caregiver: {
    conversation: ['read'],
    event: ['read', 'write'],
    memory: ['read', 'write', 'confirm'],
    summary: ['read', 'publish'],
    persona: ['read', 'write'],
  },
  family: {
    summary: ['read'],
  },
  admin: {
    conversation: ['read'],
    event: ['read'],
    memory: ['read'],
    summary: ['read'],
    persona: ['read', 'write'],
    knowledge_base: ['read', 'write'],
    system_settings: ['read', 'write'],
  },
} as const;

const ADMIN_ONLY_RESOURCES: readonly Resource[] = ['knowledge_base', 'system_settings'];

/** True if `role` may perform `action` on `resource` at all (not yet elder-scoped). */
export function hasPermission(role: UserRole, resource: Resource, action: Action): boolean {
  const allowed = PERMISSION_MATRIX[role]?.[resource];
  return allowed ? allowed.includes(action) : false;
}

/**
 * Property 11 (Elder-level data isolation): any data-access request must only
 * ever return data whose elder_id is in the requester's authorized set.
 * Admin-only resources bypass elder scoping entirely — they aren't elder data.
 */
export function validateDataAccess(
  authContext: AuthorizationContext,
  requestedElderId: string,
  resource?: Resource,
): boolean {
  if (resource && ADMIN_ONLY_RESOURCES.includes(resource)) {
    return authContext.role === 'admin';
  }
  if (authContext.role === 'admin') {
    return true;
  }
  return authContext.authorizedElderIds.includes(requestedElderId);
}

/** Combines the resource/action check with elder-scoping in one call for API handlers. */
export function authorize(
  authContext: AuthorizationContext,
  resource: Resource,
  action: Action,
  requestedElderId: string,
): boolean {
  return hasPermission(authContext.role, resource, action) && validateDataAccess(authContext, requestedElderId, resource);
}
