'use client';

import { useState } from 'react';
import type { EventSummary, EventType, ReviewStatus } from '@elderly-care/shared';

const EVENT_TYPE_LABEL: Record<EventType, string> = {
  meal: '飲食',
  activity: '活動',
  sleep: '睡眠',
  medication_statement: '用藥陳述',
  emotion: '情緒',
  important_event: '重要事件',
};

const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  auto_approved: '自動核可',
  needs_review: '待覆核',
  caregiver_confirmed: '已確認',
  caregiver_rejected: '已拒絕',
};

export interface EventTableProps {
  events: EventSummary[];
  onSave: (eventId: string, eventDate: string, content: string, reviewStatus: ReviewStatus) => Promise<void>;
}

/** Event review/correction table (B03.1, B03.4, B04.1-B04.4). Inline-editable content + review status. */
export function EventTable({ events, onSave }: EventTableProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftContent, setDraftContent] = useState('');
  const [draftStatus, setDraftStatus] = useState<ReviewStatus>('needs_review');
  const [saving, setSaving] = useState(false);

  function startEdit(event: EventSummary) {
    setEditingId(event.eventId);
    setDraftContent(event.content);
    setDraftStatus(event.reviewStatus);
  }

  async function save(event: EventSummary) {
    setSaving(true);
    try {
      await onSave(event.eventId, event.eventDate, draftContent, draftStatus);
      setEditingId(null);
    } finally {
      setSaving(false);
    }
  }

  if (events.length === 0) return <p style={{ color: '#718096' }}>沒有符合條件的事件紀錄。</p>;

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 15 }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>
          <th style={{ padding: 8 }}>日期</th>
          <th style={{ padding: 8 }}>類型</th>
          <th style={{ padding: 8 }}>內容</th>
          <th style={{ padding: 8 }}>信心分數</th>
          <th style={{ padding: 8 }}>審查狀態</th>
          <th style={{ padding: 8 }}>來源／修正紀錄</th>
          <th style={{ padding: 8 }}>操作</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.eventId} style={{ borderBottom: '1px solid #edf2f7' }}>
            <td style={{ padding: 8 }}>{event.eventDate}</td>
            <td style={{ padding: 8 }}>{EVENT_TYPE_LABEL[event.eventType]}</td>
            <td style={{ padding: 8, maxWidth: 260 }}>
              {editingId === event.eventId ? (
                <textarea
                  value={draftContent}
                  onChange={(e) => setDraftContent(e.target.value)}
                  style={{ width: '100%' }}
                />
              ) : (
                event.content
              )}
            </td>
            <td style={{ padding: 8 }}>{(event.confidence * 100).toFixed(0)}%</td>
            <td style={{ padding: 8 }}>
              {editingId === event.eventId ? (
                <select value={draftStatus} onChange={(e) => setDraftStatus(e.target.value as ReviewStatus)}>
                  {Object.entries(REVIEW_STATUS_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              ) : (
                REVIEW_STATUS_LABEL[event.reviewStatus]
              )}
            </td>
            <td style={{ padding: 8, fontSize: 12, color: '#718096' }}>
              對話：{event.sourceConversationId}
              {event.correctionCount > 0 && <div>已修正 {event.correctionCount} 次</div>}
            </td>
            <td style={{ padding: 8 }}>
              {editingId === event.eventId ? (
                <button type="button" disabled={saving} onClick={() => save(event)}>
                  儲存
                </button>
              ) : (
                <button type="button" onClick={() => startEdit(event)}>
                  修正
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
