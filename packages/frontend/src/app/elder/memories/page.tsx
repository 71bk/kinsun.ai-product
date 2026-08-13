'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ElderShell } from '@/components/elder/ElderShell';
import { MemoryCard, type ElderMemoryCommand } from '@/components/memory/MemoryCard';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { ApiRequestError } from '@/lib/api/client';
import { activeLongTermMemoryConsent, listConsents, type ConsentRecord } from '@/lib/api/consent';
import {
  confirmMemoryAsElder,
  deferMemoryAsElder,
  deleteMemoryAsElder,
  listMemories,
  rejectMemoryAsElder,
  type MemoryListView,
  type MemoryView,
} from '@/lib/api/memories';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './ElderMemoriesPage.module.css';

function memoryError(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 409) {
    return '記憶內容或同意版本剛剛已變更，請重新整理後再試。';
  }
  if (error instanceof ApiRequestError && (error.status === 403 || error.status === 404)) {
    return '目前身分不能讀取或操作這些記憶。';
  }
  return '目前無法讀取記憶，請稍後再試。';
}

export default function ElderMemoriesPage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [configFailed, setConfigFailed] = useState(false);
  const [consent, setConsent] = useState<ConsentRecord | null | undefined>(undefined);
  const [memories, setMemories] = useState<MemoryListView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );
  const elderId = config?.elderId ?? '';

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig()
      .then((next) => {
        if (!cancelled) setConfig(next);
      })
      .catch(() => {
        if (!cancelled) setConfigFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async () => {
    if (!elderId) return;
    setError(null);
    setMemories(null);
    try {
      const consents = await listConsents(apiConfig, elderId);
      const longTermMemory = activeLongTermMemoryConsent(consents);
      setConsent(longTermMemory);
      if (!longTermMemory) return;
      setMemories(await listMemories(apiConfig, elderId));
    } catch (caught) {
      setError(memoryError(caught));
    }
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (config?.credentialStatus === 'present' && elderId) void load();
  }, [config?.credentialStatus, elderId, load]);

  async function handleCommand(memory: MemoryView, command: ElderMemoryCommand) {
    try {
      if (command === 'confirm') await confirmMemoryAsElder(apiConfig, elderId, memory);
      if (command === 'defer') await deferMemoryAsElder(apiConfig, elderId, memory);
      if (command === 'reject') await rejectMemoryAsElder(apiConfig, elderId, memory);
      if (command === 'delete') await deleteMemoryAsElder(apiConfig, elderId, memory);
      await load();
    } catch (caught) {
      setError(memoryError(caught));
      throw caught;
    }
  }

  if (configFailed || config?.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason="無法確認登入憑證狀態；系統已停止，不會略過認證。" />;
  }
  if (!config) {
    return (
      <main className={styles.bootstrap} data-surface="voice" role="status">
        正在確認登入狀態…
      </main>
    );
  }
  if (config.credentialStatus !== 'present' || !elderId) {
    return <NotLoggedIn reason="請先以長者身分登入，再查看長期記憶。" />;
  }

  return (
    <ElderShell>
      <main className={styles.page}>
        <header className={styles.header}>
          <span className={styles.eyebrow}>候選不是事實</span>
          <h1>我的記憶</h1>
          <p>小暖只能在您明確按下確認後，才把候選內容變成正式長期記憶。</p>
        </header>

        {error && (
          <ErrorState
            action={
              <button className={styles.retry} onClick={() => void load()} type="button">
                重新整理
              </button>
            }
            description={error}
          />
        )}

        {consent === undefined && !error && (
          <p aria-live="polite" className={styles.loading}>
            正在確認長期記憶同意…
          </p>
        )}

        {consent === null && !error && (
          <section className={styles.consentRequired}>
            <h2>長期記憶尚未開啟</h2>
            <p>在您開啟 LONG_TERM_MEMORY 同意前，Core 不會回傳候選或正式記憶。</p>
            <Link href="/consent">前往同意設定</Link>
          </section>
        )}

        {consent && !memories && !error && (
          <p aria-live="polite" className={styles.loading}>
            正在讀取您的記憶…
          </p>
        )}

        {memories && (
          <>
            <section aria-labelledby="memory-candidate-title" className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 id="memory-candidate-title">等您確認</h2>
                  <p>可以確認、拒絕或稍後再問；沒有選擇前不會成為正式記憶。</p>
                </div>
                <span>{memories.candidates.length} 筆目前載入</span>
              </div>
              {memories.candidates.length === 0 ? (
                <EmptyState description="目前沒有等待您確認的候選記憶。" title="沒有待確認內容" />
              ) : (
                <div className={styles.list}>
                  {memories.candidates.map((memory) => (
                    <MemoryCard
                      key={memory.memoryId}
                      memory={memory}
                      mode="candidate"
                      onCommand={handleCommand}
                    />
                  ))}
                </div>
              )}
              {memories.candidateHasMore && (
                <p className={styles.pageNotice}>Core 還有下一頁，因此上方數字不是完整總數。</p>
              )}
            </section>

            <section aria-labelledby="memory-active-title" className={styles.section}>
              <div className={styles.sectionHeader}>
                <div>
                  <h2 id="memory-active-title">已確認的記憶</h2>
                  <p>只有 ACTIVE 狀態會在安全條件成立時提供給陪伴服務。</p>
                </div>
                <span>{memories.confirmed.length} 筆目前載入</span>
              </div>
              {memories.confirmed.length === 0 ? (
                <EmptyState description="目前還沒有您確認過的長期記憶。" title="尚無正式記憶" />
              ) : (
                <div className={styles.list}>
                  {memories.confirmed.map((memory) => (
                    <MemoryCard
                      key={memory.memoryId}
                      memory={memory}
                      mode="active"
                      onCommand={handleCommand}
                    />
                  ))}
                </div>
              )}
              {memories.confirmedHasMore && (
                <p className={styles.pageNotice}>Core 還有下一頁，因此上方數字不是完整總數。</p>
              )}
            </section>
          </>
        )}
      </main>
    </ElderShell>
  );
}
