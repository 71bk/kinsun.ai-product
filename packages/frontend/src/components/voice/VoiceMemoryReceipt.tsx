'use client';

import { ArrowCounterClockwise } from '@phosphor-icons/react';
import { useEffect, useRef, useState } from 'react';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import type { CompanionTurn } from '@/lib/api/companion';
import { deleteMemoryAsElder } from '@/lib/api/memories';
import { translate } from '@/lib/i18n/messages';
import styles from './VoiceMemoryReceipt.module.css';

export function VoiceMemoryReceipt({
  apiConfig,
  elderId,
  memory,
}: {
  apiConfig: ApiConfig;
  elderId: string;
  memory: NonNullable<CompanionTurn['memory_updates']>[number];
}) {
  const [busy, setBusy] = useState(false);
  const [removed, setRemoved] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const t = (key: Parameters<typeof translate>[1]) => translate('zh-Hant', key);

  async function undo() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      await deleteMemoryAsElder(apiConfig, elderId, {
        memoryId: memory.memory_id,
        version: memory.version,
      });
      if (mounted.current) setRemoved(true);
    } catch (cause) {
      if (!mounted.current) return;
      if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) {
        setRemoved(true);
      }
      setError(
        t(
          cause instanceof ApiRequestError && cause.status === 409
            ? 'voiceMemory.changed'
            : 'voiceMemory.unavailable',
        ),
      );
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <div className={styles.card} aria-live="polite">
      {!removed && (
        <>
          <p>
            <strong>{t('voiceMemory.saved')}</strong>：{memory.content}
          </p>
          <p className={styles.source}>{t('voiceMemory.source')}</p>
          <button className={styles.undo} type="button" disabled={busy} onClick={() => void undo()}>
            <ArrowCounterClockwise size={32} weight="fill" aria-hidden="true" />
            {t(busy ? 'voiceMemory.undoing' : 'voiceMemory.undo')}
          </button>
        </>
      )}
      {removed && !error && <p role="status">{t('voiceMemory.removed')}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
