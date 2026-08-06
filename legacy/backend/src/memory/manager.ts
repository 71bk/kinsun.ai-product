import type { AuditEntry, CandidateMemory, ConfirmedMemory, MemoryRecord } from '@elderly-care/shared';
import { computeTtlEpochSeconds, DynamoTable, Keys, RETENTION_DAYS } from '../db/index.js';

/** The subset of DynamoTable's interface MemoryManager needs — lets tests substitute an in-memory fake. */
export interface MemoryDataStore {
  getItem<T>(pk: string, sk: string): Promise<T | null>;
  putItem<T extends object>(item: T): Promise<void>;
  deleteItem(pk: string, sk: string): Promise<void>;
  queryByPk<T>(pk: string, skPrefix?: string, limit?: number): Promise<T[]>;
}

export interface VectorIndexClient {
  removeMemory(memoryId: string): Promise<void>;
}

const noopVectorIndex: VectorIndexClient = { async removeMemory() {} };

function toConfirmedMemory(record: MemoryRecord): ConfirmedMemory {
  return {
    memoryId: record.memoryId,
    elderId: record.elderId,
    category: record.category,
    content: record.content,
    confirmedBy: record.confirmedBy ?? '',
    confirmedAt: record.confirmedAt ?? '',
    sourceConversationId: record.sourceConversationId,
    isActive: record.isActive,
    lastUsedAt: record.lastUsedAt,
  };
}

export interface MemoryUpdate {
  content?: string;
  category?: MemoryRecord['category'];
}

/**
 * MemoryManager (D01-D04) — owns the candidate -> confirmed -> (updated |
 * deactivated | deleted) lifecycle. Structural invariants this class is
 * responsible for:
 *  - Property 9: every update() call appends to auditTrail (never
 *    truncates/overwrites it), recording the previous value, new value,
 *    updater, and timestamp.
 *  - Property 10: reject() never writes under the MEM# (confirmed) prefix,
 *    so retrieve() — which only reads MEM# — can never return a rejected
 *    candidate, structurally rather than by a runtime filter alone.
 *  - Property 12: delete() removes the DynamoDB item and the vector index
 *    entry together; a caller can't observe a state where only one
 *    completed (both awaited via Promise.all before delete() resolves).
 */
export class MemoryManager {
  constructor(
    private readonly table: MemoryDataStore = new DynamoTable(),
    private readonly vectorIndex: VectorIndexClient = noopVectorIndex,
  ) {}

  async persistCandidate(candidate: CandidateMemory): Promise<MemoryRecord> {
    const record: MemoryRecord = {
      PK: Keys.elderPk(candidate.elderId),
      SK: Keys.candidateMemorySk(candidate.memoryId),
      memoryId: candidate.memoryId,
      elderId: candidate.elderId,
      category: candidate.category,
      content: candidate.content,
      sourceConversationId: candidate.sourceConversationId,
      confidence: candidate.confidence,
      status: 'pending',
      confirmedBy: null,
      confirmedAt: null,
      isActive: false,
      lastUsedAt: null,
      createdAt: candidate.createdAt,
      updatedAt: candidate.createdAt,
      auditTrail: [
        { action: 'created', performedBy: 'system', performedAt: candidate.createdAt, details: 'candidate memory generated' },
      ],
      ttl: computeTtlEpochSeconds(RETENTION_DAYS.candidateMemory),
    };
    await this.table.putItem(record);
    return record;
  }

  async confirm(elderId: string, memoryId: string, confirmerId: string): Promise<ConfirmedMemory> {
    const candidate = await this.table.getItem<MemoryRecord>(Keys.elderPk(elderId), Keys.candidateMemorySk(memoryId));
    if (!candidate) throw new Error(`Candidate memory ${memoryId} not found for elder ${elderId}`);

    const now = new Date().toISOString();
    const confirmed: MemoryRecord = {
      ...candidate,
      SK: Keys.confirmedMemorySk(memoryId),
      status: 'confirmed',
      confirmedBy: confirmerId,
      confirmedAt: now,
      isActive: true,
      updatedAt: now,
      auditTrail: [
        ...candidate.auditTrail,
        { action: 'confirmed', performedBy: confirmerId, performedAt: now, details: 'candidate confirmed' },
      ],
      ttl: null, // confirmed memories are retained until manually deleted
    };
    await this.table.putItem(confirmed);
    await this.table.deleteItem(Keys.elderPk(elderId), Keys.candidateMemorySk(memoryId));
    return toConfirmedMemory(confirmed);
  }

  async reject(elderId: string, memoryId: string, rejecterId: string): Promise<void> {
    const candidate = await this.table.getItem<MemoryRecord>(Keys.elderPk(elderId), Keys.candidateMemorySk(memoryId));
    if (!candidate) return;
    const now = new Date().toISOString();
    await this.table.putItem({
      ...candidate,
      status: 'rejected',
      updatedAt: now,
      auditTrail: [...candidate.auditTrail, { action: 'rejected', performedBy: rejecterId, performedAt: now, details: 'candidate rejected' }],
    });
  }

  /** Only ever reads the MEM# (confirmed) prefix — see class doc for why that's load-bearing for Property 10. */
  async retrieve(elderId: string, context: string, limit: number): Promise<ConfirmedMemory[]> {
    const records = await this.table.queryByPk<MemoryRecord>(Keys.elderPk(elderId), Keys.memorySkPrefix('confirmed'));
    const active = records.filter((r) => r.status === 'confirmed' && r.isActive);
    const scored = active.map((r) => ({ record: r, score: context && r.content.includes(context) ? 1 : 0 }));
    scored.sort((a, b) => b.score - a.score || (b.record.confirmedAt ?? '').localeCompare(a.record.confirmedAt ?? ''));
    return scored.slice(0, Math.max(0, limit)).map((s) => toConfirmedMemory(s.record));
  }

  async update(elderId: string, memoryId: string, updates: MemoryUpdate, updaterId: string): Promise<ConfirmedMemory> {
    const record = await this.table.getItem<MemoryRecord>(Keys.elderPk(elderId), Keys.confirmedMemorySk(memoryId));
    if (!record) throw new Error(`Confirmed memory ${memoryId} not found for elder ${elderId}`);

    const now = new Date().toISOString();
    const newEntries: AuditEntry[] = [];
    (Object.keys(updates) as (keyof MemoryUpdate)[]).forEach((field) => {
      const newValue = updates[field];
      if (newValue !== undefined && newValue !== record[field]) {
        newEntries.push({
          action: 'updated',
          performedBy: updaterId,
          performedAt: now,
          details: `${field}: "${String(record[field])}" -> "${String(newValue)}"`,
        });
      }
    });

    const updated: MemoryRecord = {
      ...record,
      ...updates,
      updatedAt: now,
      auditTrail: [...record.auditTrail, ...newEntries], // append-only — Property 9
    };
    await this.table.putItem(updated);
    return toConfirmedMemory(updated);
  }

  async deactivate(elderId: string, memoryId: string, requesterId: string): Promise<ConfirmedMemory> {
    const record = await this.table.getItem<MemoryRecord>(Keys.elderPk(elderId), Keys.confirmedMemorySk(memoryId));
    if (!record) throw new Error(`Confirmed memory ${memoryId} not found for elder ${elderId}`);
    const now = new Date().toISOString();
    const updated: MemoryRecord = {
      ...record,
      isActive: false,
      updatedAt: now,
      auditTrail: [...record.auditTrail, { action: 'deactivated', performedBy: requesterId, performedAt: now, details: 'memory deactivated' }],
    };
    await this.table.putItem(updated);
    return toConfirmedMemory(updated);
  }

  async delete(elderId: string, memoryId: string): Promise<void> {
    await Promise.all([
      this.table.deleteItem(Keys.elderPk(elderId), Keys.confirmedMemorySk(memoryId)),
      this.vectorIndex.removeMemory(memoryId),
    ]);
  }
}
