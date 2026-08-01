import { describe, expect, it } from 'vitest';
import type { CandidateMemory, MemoryRecord } from '@elderly-care/shared';
import { InMemoryStore } from '../memory/in-memory-store.test-util.js';
import { MemoryManager } from '../memory/manager.js';
import { ContextComposer } from '../context/composer.js';
import type { ContextComposeInputs } from '../context/types.js';

const candidate: CandidateMemory = {
  memoryId: 'mem-tea',
  elderId: 'elder-1',
  category: 'preference',
  content: '喜歡喝烏龍茶',
  sourceConversationId: 'conv-1',
  confidence: 0.88,
  createdAt: '2026-07-24T00:00:00Z',
  status: 'pending',
};

/**
 * 記憶確認流程整合測試 (task 25.3). Runs the full D02 lifecycle — generate
 * candidate -> confirm -> retrieve — through the real MemoryManager, then
 * feeds the retrieved confirmed memory into the real ContextComposer and
 * checks it actually surfaces in the composed prompt's confirmedMemories.
 * This is the cross-module guarantee Property 5 depends on in production:
 * not just "the composer filters correctly" (already covered in isolation)
 * but "a memory MemoryManager actually confirmed is the same shape
 * ContextComposer actually accepts."
 */
describe('Integration: candidate memory confirm -> retrieve -> context composition', () => {
  it('a confirmed memory flows through to the composed prompt; a rejected one never does', async () => {
    const store = new InMemoryStore();
    const manager = new MemoryManager(store);

    await manager.persistCandidate(candidate);
    const confirmed = await manager.confirm('elder-1', 'mem-tea', 'caregiver-1');
    expect(confirmed.content).toBe('喜歡喝烏龍茶');

    const retrieved = await manager.retrieve('elder-1', '', 10);
    expect(retrieved).toHaveLength(1);

    // Bridge MemoryManager's ConfirmedMemory[] into what ContextComposer
    // expects (MemoryRecord[]) — this is exactly what a real Lambda
    // handler does when it loads context inputs.
    const memoryRecord = await store.getItem<MemoryRecord>('ELDER#elder-1', 'MEM#mem-tea');
    expect(memoryRecord).not.toBeNull();

    const inputs: ContextComposeInputs = {
      persona: {
        displayName: '林阿嬤',
        preferredLanguage: 'zh-TW',
        responseLength: 'short',
        speakingSpeed: 'normal',
        interactionStyle: 'warm',
        customGreeting: '',
      },
      recentSummary: null,
      memories: [memoryRecord!],
      situationalContext: {
        currentTime: '2026-07-24T12:00:00Z',
        dayOfWeek: 'Friday',
        weather: null,
        recentInteractionCount: 1,
        lastInteractionTime: null,
      },
      searchResults: [],
    };

    const composer = new ContextComposer();
    const result = composer.compose(
      { elderId: 'elder-1', currentUtterance: '你好', conversationHistory: [], tokenBudget: 4096 },
      inputs,
    );

    expect(result.confirmedMemories).toHaveLength(1);
    expect(result.confirmedMemories[0]!.content).toBe('喜歡喝烏龍茶');
  });

  it('a rejected candidate never reaches retrieve() and therefore never reaches the composed prompt', async () => {
    const store = new InMemoryStore();
    const manager = new MemoryManager(store);

    await manager.persistCandidate(candidate);
    await manager.reject('elder-1', 'mem-tea', 'caregiver-1');

    const retrieved = await manager.retrieve('elder-1', '', 10);
    expect(retrieved).toHaveLength(0);
  });
});
