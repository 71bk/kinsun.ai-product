import { describe, expect, it } from 'vitest';
import { GSI1, GSI2, Keys, parseElderIdFromPk } from './keys.js';

describe('Keys', () => {
  it('builds elder-scoped PKs consistently', () => {
    expect(Keys.elderPk('e1')).toBe('ELDER#e1');
    expect(Keys.profileSk()).toBe('PROFILE');
    expect(Keys.eventSk('2026-07-24', 'evt1')).toBe('EVENT#2026-07-24#evt1');
    expect(Keys.candidateMemorySk('m1')).toBe('CMEM#m1');
    expect(Keys.confirmedMemorySk('m1')).toBe('MEM#m1');
    expect(Keys.summarySk('2026-07-24')).toBe('SUM#2026-07-24');
  });

  it('builds caregiver/family mapping keys', () => {
    expect(Keys.caregiverPk('cg1')).toBe('CG#cg1');
    expect(Keys.caregiverElderMappingSk('e1')).toBe('ELDER#e1');
    expect(Keys.familyPk('fm1')).toBe('FM#fm1');
  });

  it('builds GSI1/GSI2 keys per design.md', () => {
    expect(GSI1.pk('e1', 'meal')).toBe('ELDER#e1#EVENT_TYPE#meal');
    expect(GSI1.sk('2026-07-24')).toBe('2026-07-24');
    expect(GSI2.pk('e1', 'needs_review')).toBe('ELDER#e1#REVIEW#needs_review');
    expect(GSI2.sk('2026-07-24', 'evt1')).toBe('2026-07-24#evt1');
  });

  it('round-trips elderId from an ELDER# partition key', () => {
    expect(parseElderIdFromPk('ELDER#e1')).toBe('e1');
    expect(parseElderIdFromPk('CG#cg1')).toBeNull();
  });
});
