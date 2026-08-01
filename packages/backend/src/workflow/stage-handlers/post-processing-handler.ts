import type { ConversationRecord } from '@elderly-care/shared';
import { BedrockExtractionAdapter, EventExtractor } from '../../event-extractor/extractor.js';
import { persistEvent } from '../../event-extractor/persistence.js';
import { BedrockMemoryGenerationAdapter, MemoryCandidateGenerator } from '../../memory/generator.js';
import { MemoryManager } from '../../memory/manager.js';
import { DynamoTable } from '../../db/index.js';

export interface PostProcessingInput {
  elderId: string;
  traceId: string;
  conversationId: string;
  utterance: string;
  replyText: string;
}

/**
 * Async post-processing (design.md's sequence diagram: "par 非同步處理" —
 * event extraction and candidate-memory generation run in parallel with,
 * not blocking, the elder's response). The Router Lambda fire-and-forget
 * invokes this after a turn completes, so it never adds latency to the
 * <5s voice interaction budget. Failures here are logged, never
 * surfaced to the elder — a missed event/memory extraction shouldn't
 * retroactively fail a conversation that already got its reply.
 */
export async function handler(input: PostProcessingInput): Promise<void> {
  const table = new DynamoTable();
  const conversation: ConversationRecord = {
    PK: `ELDER#${input.elderId}`,
    SK: `CONV#post-processing#${input.conversationId}`,
    conversationId: input.conversationId,
    elderId: input.elderId,
    startTime: new Date().toISOString(),
    endTime: new Date().toISOString(),
    turns: [
      { role: 'elder', content: input.utterance, timestamp: new Date().toISOString(), language: 'zh-TW' },
      { role: 'assistant', content: input.replyText, timestamp: new Date().toISOString(), language: 'zh-TW' },
    ],
    asrMetadata: null,
    status: 'completed',
    traceId: input.traceId,
    audioS3Key: null,
    ttl: 0,
  };

  const [eventOutcome, memoryOutcome] = await Promise.all([
    new EventExtractor(new BedrockExtractionAdapter()).extract(conversation).catch((err) => {
      console.error('[post-processing] event extraction failed', err instanceof Error ? err.message : err);
      return { valid: [], rejected: [] };
    }),
    new MemoryCandidateGenerator(new BedrockMemoryGenerationAdapter()).generateCandidates(conversation).catch((err) => {
      console.error('[post-processing] memory candidate generation failed', err instanceof Error ? err.message : err);
      return { valid: [], rejected: [] };
    }),
  ]);

  const memoryManager = new MemoryManager(table);
  await Promise.all([
    ...eventOutcome.valid.map((event) => persistEvent(table, event).catch((err) => console.error('[post-processing] failed to persist event', err))),
    ...memoryOutcome.valid.map((candidate) =>
      memoryManager.persistCandidate(candidate).catch((err) => console.error('[post-processing] failed to persist candidate memory', err)),
    ),
  ]);
}
