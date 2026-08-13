'use client';

import { useState } from 'react';
import { EvidenceBlock } from '@/components/care/EvidenceBlock';
import { StateCard } from '@/components/StateCard';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import type { MemoryView } from '@/lib/api/memories';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './MemoryList.module.css';

export interface MemoryListProps {
  candidates: MemoryView[];
  confirmed: MemoryView[];
  onReject: (memory: MemoryView) => Promise<void>;
  onDelete: (memory: MemoryView) => Promise<void>;
}

type PendingAction = { kind: 'reject' | 'delete'; memory: MemoryView } | null;

export function MemoryList({ candidates, confirmed, onReject, onDelete }: MemoryListProps) {
  const { t, formatDateTime } = useLocale();
  const [pending, setPending] = useState<PendingAction>(null);
  const [busy, setBusy] = useState(false);

  async function confirmAction() {
    if (!pending) return;
    setBusy(true);
    try {
      if (pending.kind === 'reject') await onReject(pending.memory);
      else await onDelete(pending.memory);
      setPending(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.list}>
      <section aria-labelledby="memory-candidates-title">
        <h2 className={styles.heading} id="memory-candidates-title">
          {t('memory.candidatesTitle', { count: candidates.length })}
        </h2>
        {candidates.length === 0 ? (
          <EmptyState
            description={t('memory.candidatesEmpty')}
            title={t('memory.candidatesEmptyTitle')}
          />
        ) : (
          <div className={styles.cards}>
            {candidates.map((memory) => (
              <StateCard
                actions={
                  <button
                    className={styles.destructiveButton}
                    onClick={() => setPending({ kind: 'reject', memory })}
                    type="button"
                  >
                    {t('memory.reject')}
                  </button>
                }
                key={memory.memoryId}
                meta={
                  <EvidenceBlock
                    consentVersion={memory.consentVersion}
                    sourceCount={memory.sourceEventIds.length}
                    version={memory.version}
                  />
                }
                state="candidate"
                title={t(`memoryType.${memory.memoryType}` as MessageKey)}
              >
                {memory.content}
              </StateCard>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="confirmed-memories-title">
        <h2 className={styles.heading} id="confirmed-memories-title">
          {t('memory.confirmedTitle', { count: confirmed.length })}
        </h2>
        {confirmed.length === 0 ? (
          <EmptyState
            description={t('memory.confirmedEmpty')}
            title={t('memory.confirmedEmptyTitle')}
          />
        ) : (
          <div className={styles.cards}>
            {confirmed.map((memory) => (
              <StateCard
                actions={
                  <button
                    className={styles.destructiveButton}
                    onClick={() => setPending({ kind: 'delete', memory })}
                    type="button"
                  >
                    {t('memory.delete')}
                  </button>
                }
                key={memory.memoryId}
                meta={
                  <div className={styles.memoryMeta}>
                    <EvidenceBlock
                      consentVersion={memory.consentVersion}
                      sourceCount={memory.sourceEventIds.length}
                      version={memory.version}
                    />
                    <span>
                      {t('memory.confirmedAt', { at: formatDateTime(memory.confirmedAt) })}
                    </span>
                  </div>
                }
                state="confirmed"
                title={t(`memoryType.${memory.memoryType}` as MessageKey)}
              >
                {memory.content}
              </StateCard>
            ))}
          </div>
        )}
      </section>

      <ConfirmationDialog
        busy={busy}
        confirmLabel={pending?.kind === 'delete' ? t('memory.delete') : t('memory.reject')}
        description={
          pending?.kind === 'delete'
            ? t('memory.deleteConfirmDescription')
            : t('memory.rejectConfirmDescription')
        }
        onCancel={() => setPending(null)}
        onConfirm={() => void confirmAction()}
        open={pending !== null}
        title={
          pending?.kind === 'delete'
            ? t('memory.deleteConfirmTitle')
            : t('memory.rejectConfirmTitle')
        }
        tone="destructive"
      />
    </div>
  );
}
