'use client';

import { Brain, CheckCircle, Clock, Prohibit, Trash } from '@phosphor-icons/react';
import { useState } from 'react';
import { EvidenceBlock } from '@/components/care/EvidenceBlock';
import { StateBadge } from '@/components/StateCard';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import type { MemoryView } from '@/lib/api/memories';
import styles from './MemoryCard.module.css';

export type ElderMemoryCommand = 'confirm' | 'defer' | 'reject' | 'delete';

const TYPE_LABEL: Record<MemoryView['memoryType'], string> = {
  PREFERENCE: '偏好',
  IMPORTANT_RELATIONSHIP: '重要關係',
  ROUTINE: '生活習慣',
  COMMUNICATION_PREFERENCE: '溝通偏好',
  PERSONAL_HISTORY: '個人經歷',
};

const COMMAND_COPY: Record<
  ElderMemoryCommand,
  { label: string; title: string; description: string }
> = {
  confirm: {
    label: '是，請記住',
    title: '確認要記住這件事？',
    description: '只有這一筆候選內容會成為 ACTIVE 長期記憶。這不是健康診斷或醫療事實。',
  },
  defer: {
    label: '稍後再問',
    title: '稍後再決定？',
    description: '這筆內容仍是候選資料，不會被當成已確認的事實。',
  },
  reject: {
    label: '不是這樣',
    title: '確認拒絕這筆候選？',
    description: 'Core 會把這筆候選標示為 REJECTED，不會成為長期記憶。',
  },
  delete: {
    label: '刪除這筆記憶',
    title: '確認刪除這筆記憶？',
    description: 'Core 會把這筆正式記憶標示為 DELETED。這項操作需要重新驗證目前版本。',
  },
};

export function MemoryCard({
  memory,
  mode,
  onCommand,
}: {
  memory: MemoryView;
  mode: 'candidate' | 'active';
  onCommand: (memory: MemoryView, command: ElderMemoryCommand) => Promise<void>;
}) {
  const [pending, setPending] = useState<ElderMemoryCommand | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmCommand() {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      await onCommand(memory, pending);
      setPending(null);
    } catch {
      setError('這次操作沒有完成，內容可能已變更，請重新整理後再試。');
    } finally {
      setBusy(false);
    }
  }

  const state = mode === 'active' ? 'confirmed' : 'candidate';
  const stateLabel =
    mode === 'active' ? '已確認' : memory.status === 'DEFERRED' ? '稍後再問' : '等待您確認';

  return (
    <article className={styles.card} data-mode={mode}>
      <div className={styles.header}>
        <div>
          <span className={styles.kicker}>
            <Brain aria-hidden="true" size={26} weight="fill" />
            {TYPE_LABEL[memory.memoryType]}
          </span>
          <h3>{mode === 'active' ? '小暖已記住' : '小暖想記住'}</h3>
        </div>
        <StateBadge label={stateLabel} state={state} />
      </div>
      <p className={styles.content}>{memory.content}</p>
      <EvidenceBlock
        consentVersion={memory.consentVersion}
        sourceCount={memory.sourceEventIds.length}
        version={memory.version}
      />
      {mode === 'active' && memory.confirmedAt && (
        <p className={styles.confirmedAt}>
          確認時間：{new Date(memory.confirmedAt).toLocaleString('zh-TW')}
        </p>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      <div className={styles.actions}>
        {mode === 'candidate' ? (
          <>
            <button className={styles.confirm} onClick={() => setPending('confirm')} type="button">
              <CheckCircle aria-hidden="true" size={28} weight="fill" />
              是，請記住
            </button>
            {memory.status !== 'DEFERRED' && (
              <button className={styles.defer} onClick={() => setPending('defer')} type="button">
                <Clock aria-hidden="true" size={28} />
                稍後再問
              </button>
            )}
            <button className={styles.reject} onClick={() => setPending('reject')} type="button">
              <Prohibit aria-hidden="true" size={28} />
              不是這樣
            </button>
          </>
        ) : (
          <button className={styles.reject} onClick={() => setPending('delete')} type="button">
            <Trash aria-hidden="true" size={28} />
            刪除這筆記憶
          </button>
        )}
      </div>
      <ConfirmationDialog
        busy={busy}
        confirmLabel={pending ? COMMAND_COPY[pending].label : '確認'}
        description={pending ? COMMAND_COPY[pending].description : ''}
        onCancel={() => setPending(null)}
        onConfirm={() => void confirmCommand()}
        open={pending !== null}
        title={pending ? COMMAND_COPY[pending].title : ''}
        tone={pending === 'reject' || pending === 'delete' ? 'destructive' : 'default'}
      />
    </article>
  );
}
