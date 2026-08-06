import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { CandidateMemory, MemoryCategory } from '@elderly-care/shared';
import { InMemoryStore } from './in-memory-store.test-util.js';
import { MemoryManager, type VectorIndexClient } from './manager.js';

const categoryArb = fc.constantFrom<MemoryCategory>('preference', 'relationship', 'routine', 'health_condition', 'life_event');

function candidateArb(elderId: string): fc.Arbitrary<CandidateMemory> {
  return fc.record({
    memoryId: fc.uuid(),
    elderId: fc.constant(elderId),
    category: categoryArb,
    content: fc.string({ minLength: 1, maxLength: 50 }),
    sourceConversationId: fc.uuid(),
    confidence: fc.float({ min: 0, max: 1, noNaN: true }),
    createdAt: fc.constant('2026-07-24T00:00:00Z'),
    status: fc.constant('pending' as const),
  });
}

/**
 * Feature: elderly-care-ai-companion, Property 10: 拒絕的記憶永不持久化為已確認.
 * For any sequence of confirm/reject operations, a rejected candidate must
 * never be returned by retrieve() (which only surfaces confirmed+active
 * memories).
 */
describe('Property 10: Rejected memories never surface as confirmed', () => {
  it('retrieve() only ever returns memories that were explicitly confirmed', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(candidateArb('elder-1'), { minLength: 1, maxLength: 10 }),
        fc.array(fc.boolean(), { minLength: 1, maxLength: 10 }),
        async (candidates, decisions) => {
          const store = new InMemoryStore();
          const manager = new MemoryManager(store);

          const confirmedIds = new Set<string>();
          for (let i = 0; i < candidates.length; i++) {
            const candidate = candidates[i]!;
            await manager.persistCandidate(candidate);
            const shouldConfirm = decisions[i % decisions.length]!;
            if (shouldConfirm) {
              await manager.confirm('elder-1', candidate.memoryId, 'cg-1');
              confirmedIds.add(candidate.memoryId);
            } else {
              await manager.reject('elder-1', candidate.memoryId, 'cg-1');
            }
          }

          const retrieved = await manager.retrieve('elder-1', '', 1000);
          const retrievedIds = new Set(retrieved.map((m) => m.memoryId));

          expect(retrievedIds).toEqual(confirmedIds);
        },
      ),
      { numRuns: 100 },
    );
  });
});

/**
 * Feature: elderly-care-ai-companion, Property 9: 修改稽核完整性.
 * For any sequence of modifications, auditTrail must record the value
 * before and after each change, the performer, and the timestamp — and
 * never be overwritten by a later operation (append-only).
 */
describe('Property 9: Modification audit trail completeness', () => {
  it('auditTrail only ever grows and preserves every prior entry across a sequence of updates', async () => {
    await fc.assert(
      fc.asyncProperty(
        candidateArb('elder-1'),
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 1, maxLength: 8 }),
        async (candidate, newContents) => {
          const store = new InMemoryStore();
          const manager = new MemoryManager(store);
          await manager.persistCandidate(candidate);
          await manager.confirm('elder-1', candidate.memoryId, 'cg-1');

          let previousAuditTrail: unknown[] = [];
          for (const newContent of newContents) {
            await manager.update('elder-1', candidate.memoryId, { content: newContent }, 'cg-2');
            const record = await store.getItem<{ auditTrail: unknown[] }>(
              `ELDER#elder-1`,
              `MEM#${candidate.memoryId}`,
            );
            const currentTrail = record!.auditTrail;
            // Every entry present before this update must still be present, in the same order.
            expect(currentTrail.slice(0, previousAuditTrail.length)).toEqual(previousAuditTrail);
            expect(currentTrail.length).toBeGreaterThanOrEqual(previousAuditTrail.length);
            previousAuditTrail = currentTrail;
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('each recorded update entry captures performer and a before->after detail string', async () => {
    const store = new InMemoryStore();
    const manager = new MemoryManager(store);
    const candidate: CandidateMemory = {
      memoryId: 'm1',
      elderId: 'elder-1',
      category: 'preference',
      content: '喜歡喝茶',
      sourceConversationId: 'c1',
      confidence: 0.9,
      createdAt: '2026-07-24T00:00:00Z',
      status: 'pending',
    };
    await manager.persistCandidate(candidate);
    await manager.confirm('elder-1', 'm1', 'cg-1');
    const updated = await manager.update('elder-1', 'm1', { content: '喜歡喝烏龍茶' }, 'cg-2');
    expect(updated.content).toBe('喜歡喝烏龍茶');

    const record = await store.getItem<{ auditTrail: { action: string; performedBy: string; details: string }[] }>(
      'ELDER#elder-1',
      'MEM#m1',
    );
    const updateEntry = record!.auditTrail.find((e) => e.action === 'updated');
    expect(updateEntry?.performedBy).toBe('cg-2');
    expect(updateEntry?.details).toContain('喜歡喝茶');
    expect(updateEntry?.details).toContain('喜歡喝烏龍茶');
  });
});

/**
 * Feature: elderly-care-ai-companion, Property 12: 刪除操作跨儲存完整性.
 * For any deletion, the memory must be removed from every storage location
 * (DynamoDB and the vector index) — a caller can't observe partial deletion.
 */
describe('Property 12: Cross-store deletion completeness', () => {
  it('delete() removes the memory from both DynamoDB and the vector index', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(candidateArb('elder-1'), { minLength: 1, maxLength: 8 }),
        fc.array(fc.boolean(), { minLength: 1, maxLength: 8 }),
        async (candidates, deleteDecisions) => {
          const store = new InMemoryStore();
          const vectorIndexState = new Set<string>();
          const vectorIndex: VectorIndexClient = {
            async removeMemory(memoryId) {
              vectorIndexState.delete(memoryId);
            },
          };
          const manager = new MemoryManager(store, vectorIndex);

          for (const candidate of candidates) {
            await manager.persistCandidate(candidate);
            await manager.confirm('elder-1', candidate.memoryId, 'cg-1');
            vectorIndexState.add(candidate.memoryId); // simulate the memory having been indexed
          }

          const toDelete = candidates.filter((_, i) => deleteDecisions[i % deleteDecisions.length]);
          for (const candidate of toDelete) {
            await manager.delete('elder-1', candidate.memoryId);
          }

          for (const candidate of toDelete) {
            expect(store.has('ELDER#elder-1', `MEM#${candidate.memoryId}`)).toBe(false);
            expect(vectorIndexState.has(candidate.memoryId)).toBe(false);
          }
          const notDeleted = candidates.filter((c) => !toDelete.includes(c));
          for (const candidate of notDeleted) {
            expect(store.has('ELDER#elder-1', `MEM#${candidate.memoryId}`)).toBe(true);
            expect(vectorIndexState.has(candidate.memoryId)).toBe(true);
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
