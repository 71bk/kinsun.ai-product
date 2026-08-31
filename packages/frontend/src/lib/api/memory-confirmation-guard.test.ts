import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import * as memoriesApi from './memories';

function source(relativeUrl: string): string {
  return readFileSync(fileURLToPath(new URL(relativeUrl, import.meta.url)), 'utf8');
}

describe('caregiver memory confirmation guard', () => {
  it('exports only the explicit elder-self confirmation contract', () => {
    expect(memoriesApi).not.toHaveProperty('confirmMemory');
    expect(memoriesApi).toHaveProperty('confirmMemoryAsElder');

    const apiSource = source('./memories.ts');
    expect(apiSource).toContain('/confirm');
    expect(apiSource).toContain("confirmation_method: 'ELDER_UI'");
    expect(apiSource).toContain('expected_candidate_version: memory.version');
    expect(apiSource).toContain('consent_version: memory.consentVersion');
    expect(apiSource).not.toContain('CAREGIVER_REVIEW');
    expect(apiSource).not.toContain('LEGAL_REPRESENTATIVE');
    expect(apiSource).not.toContain("confirmation_method: 'VOICE'");
  });

  it('does not render or wire a confirmation action on the caregiver dashboard', () => {
    const memoryListSource = source('../../components/dashboard/MemoryList.tsx');
    const dashboardSource = source('../../app/staff/(app)/elders/[elderId]/page.tsx');

    expect(memoryListSource).not.toContain("t('memory.confirm')");
    expect(memoryListSource).not.toContain('confirmMemoryAsElder');
    expect(dashboardSource).not.toContain('confirmMemoryAsElder');
    expect(dashboardSource).not.toContain('handleConfirmMemory');
  });
});
