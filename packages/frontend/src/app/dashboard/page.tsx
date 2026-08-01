'use client';

import { useEffect, useState } from 'react';
import { ElderOverviewList } from '@/components/dashboard/ElderOverviewList';
import { getCaregiverDashboard } from '@/lib/api/dashboard';
import { getRuntimeConfig } from '@/lib/runtime-config';
import type { CaregiverDashboardEntry } from '@elderly-care/shared';

export default function CaregiverDashboardPage() {
  const [elders, setElders] = useState<CaregiverDashboardEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const config = getRuntimeConfig();
    const caregiverId = window.localStorage.getItem('elderly_care_caregiver_id') ?? '';
    getCaregiverDashboard({ apiBaseUrl: config.apiBaseUrl, token: config.token }, caregiverId)
      .then((res) => setElders(res.elders))
      .catch(() => setError('讀取資料失敗，請重新整理'));
  }, []);

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>照護者總覽</h1>
      {error && <p style={{ color: '#e53e3e' }}>{error}</p>}
      {!elders && !error && <p>載入中...</p>}
      {elders && <ElderOverviewList elders={elders} />}
    </main>
  );
}
