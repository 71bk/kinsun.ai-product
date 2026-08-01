'use client';

import type { CandidateMemory, ConfirmedMemory } from '@elderly-care/shared';

export interface MemoryListProps {
  candidates: CandidateMemory[];
  confirmed: ConfirmedMemory[];
  onConfirm: (memoryId: string) => Promise<void>;
  onReject: (memoryId: string) => Promise<void>;
  onDelete: (memoryId: string) => Promise<void>;
}

/** Candidate confirm/reject + confirmed view/delete (D02.3, D04.1). */
export function MemoryList({ candidates, confirmed, onConfirm, onReject, onDelete }: MemoryListProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <section>
        <h3 style={{ fontSize: 18, marginBottom: 8 }}>待確認候選記憶（{candidates.length}）</h3>
        {candidates.length === 0 && <p style={{ color: '#718096' }}>目前沒有待確認的候選記憶。</p>}
        {candidates.map((c) => (
          <div
            key={c.memoryId}
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 10, border: '1px solid #e2e8f0', borderRadius: 8, marginBottom: 8 }}
          >
            <div>
              <strong>[{c.category}]</strong> {c.content}
              <div style={{ fontSize: 12, color: '#718096' }}>信心分數：{(c.confidence * 100).toFixed(0)}%</div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" onClick={() => onConfirm(c.memoryId)}>
                確認
              </button>
              <button type="button" onClick={() => onReject(c.memoryId)}>
                拒絕
              </button>
            </div>
          </div>
        ))}
      </section>

      <section>
        <h3 style={{ fontSize: 18, marginBottom: 8 }}>已確認記憶（{confirmed.length}）</h3>
        {confirmed.length === 0 && <p style={{ color: '#718096' }}>目前沒有已確認的記憶。</p>}
        {confirmed.map((m) => (
          <div
            key={m.memoryId}
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 10, border: '1px solid #e2e8f0', borderRadius: 8, marginBottom: 8 }}
          >
            <div>
              <strong>[{m.category}]</strong> {m.content}
              <div style={{ fontSize: 12, color: '#718096' }}>
                確認者：{m.confirmedBy}｜確認時間：{new Date(m.confirmedAt).toLocaleString('zh-TW')}
              </div>
            </div>
            <button type="button" onClick={() => onDelete(m.memoryId)}>
              刪除
            </button>
          </div>
        ))}
      </section>
    </div>
  );
}
