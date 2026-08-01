import { describe, expect, it } from 'vitest';
import type { AuthorizationContext } from '@elderly-care/shared';
import { authorize, hasPermission, validateDataAccess } from './permissions.js';

describe('hasPermission — role permission matrix (design.md §角色權限矩陣)', () => {
  it('elder can read/confirm/delete own memories but not write events', () => {
    expect(hasPermission('elder', 'memory', 'read')).toBe(true);
    expect(hasPermission('elder', 'memory', 'confirm')).toBe(true);
    expect(hasPermission('elder', 'memory', 'delete')).toBe(true);
    expect(hasPermission('elder', 'event', 'write')).toBe(false);
  });

  it('caregiver can read/write events and manage persona', () => {
    expect(hasPermission('caregiver', 'event', 'write')).toBe(true);
    expect(hasPermission('caregiver', 'persona', 'write')).toBe(true);
    expect(hasPermission('caregiver', 'system_settings', 'read')).toBe(false);
  });

  it('only caregiver can publish summaries', () => {
    expect(hasPermission('caregiver', 'summary', 'publish')).toBe(true);
    expect(hasPermission('family', 'summary', 'publish')).toBe(false);
    expect(hasPermission('elder', 'summary', 'publish')).toBe(false);
    expect(hasPermission('admin', 'summary', 'publish')).toBe(false);
  });

  it('family can only read summaries', () => {
    expect(hasPermission('family', 'summary', 'read')).toBe(true);
    expect(hasPermission('family', 'event', 'read')).toBe(false);
    expect(hasPermission('family', 'memory', 'read')).toBe(false);
  });

  it('admin manages knowledge base and system settings', () => {
    expect(hasPermission('admin', 'knowledge_base', 'write')).toBe(true);
    expect(hasPermission('admin', 'system_settings', 'write')).toBe(true);
  });

  it('unknown resource/role combinations default to no access', () => {
    expect(hasPermission('family', 'knowledge_base', 'read')).toBe(false);
  });
});

describe('cross-elder access denial', () => {
  const caregiverContext: AuthorizationContext = {
    userId: 'cg1',
    role: 'caregiver',
    authorizedElderIds: ['elder-1', 'elder-2'],
    tenantId: 't1',
  };

  it('rejects access to an elder outside the caregiver assignment', () => {
    expect(validateDataAccess(caregiverContext, 'elder-999')).toBe(false);
  });

  it('accepts access to an assigned elder', () => {
    expect(validateDataAccess(caregiverContext, 'elder-1')).toBe(true);
  });

  it('authorize() combines permission + elder scoping and rejects when either fails', () => {
    // Right elder, wrong action for role (family cannot write events)
    const familyContext: AuthorizationContext = {
      userId: 'fm1',
      role: 'family',
      authorizedElderIds: ['elder-1'],
      tenantId: 't1',
    };
    expect(authorize(familyContext, 'event', 'write', 'elder-1')).toBe(false);

    // Right action for role, wrong elder
    expect(authorize(caregiverContext, 'event', 'write', 'elder-999')).toBe(false);

    // Right action, right elder
    expect(authorize(caregiverContext, 'event', 'write', 'elder-1')).toBe(true);
  });
});

describe('unauthorized role operations are rejected', () => {
  it('elder cannot write events even for their own elderId', () => {
    const elderContext: AuthorizationContext = {
      userId: 'elder-1',
      role: 'elder',
      authorizedElderIds: ['elder-1'],
      tenantId: 't1',
    };
    expect(authorize(elderContext, 'event', 'write', 'elder-1')).toBe(false);
  });

  it('family cannot confirm memories', () => {
    const familyContext: AuthorizationContext = {
      userId: 'fm1',
      role: 'family',
      authorizedElderIds: ['elder-1'],
      tenantId: 't1',
    };
    expect(authorize(familyContext, 'memory', 'confirm', 'elder-1')).toBe(false);
  });
});
