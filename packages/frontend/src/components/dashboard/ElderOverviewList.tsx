'use client';

import Link from 'next/link';
import type { CaregiverDashboardEntry } from '@elderly-care/shared';

export interface ElderOverviewListProps {
  elders: CaregiverDashboardEntry[];
}

const SUMMARY_STATUS_LABEL: Record<CaregiverDashboardEntry['summaryStatus'], string> = {
  generated: '已產生',
  pending: '產生中',
  failed: '產生失敗',
};

/**
 * Multi-elder overview (C01.1-C01.3). Only shows objective counts — no
 * undefined risk labels like "高風險"/"異常" (C01.3). The server has
 * already scoped `elders` to ones this caregiver is authorized for.
 */
export function ElderOverviewList({ elders }: ElderOverviewListProps) {
  if (elders.length === 0) {
    return <p style={{ color: '#718096' }}>目前沒有負責的長者資料。</p>;
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #e2e8f0' }}>
          <th style={{ padding: 8 }}>長者</th>
          <th style={{ padding: 8 }}>最後互動時間</th>
          <th style={{ padding: 8 }}>今日互動次數</th>
          <th style={{ padding: 8 }}>摘要狀態</th>
          <th style={{ padding: 8 }}>待覆核事件</th>
        </tr>
      </thead>
      <tbody>
        {elders.map((elder) => (
          <tr key={elder.elderId} style={{ borderBottom: '1px solid #edf2f7' }}>
            <td style={{ padding: 8 }}>
              <Link href={`/dashboard/${elder.elderId}`} style={{ color: '#2b6cb0' }}>
                {elder.elderName}
              </Link>
            </td>
            <td style={{ padding: 8 }}>{elder.lastInteractionAt ? new Date(elder.lastInteractionAt).toLocaleString('zh-TW') : '尚無互動'}</td>
            <td style={{ padding: 8 }}>{elder.todayInteractionCount}</td>
            <td style={{ padding: 8 }}>{SUMMARY_STATUS_LABEL[elder.summaryStatus]}</td>
            <td style={{ padding: 8 }}>{elder.pendingReviewCount > 0 ? elder.pendingReviewCount : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
