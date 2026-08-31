'use client';

import { CalendarCheck, CheckCircle, ClockCountdown, Prohibit, Timer } from '@phosphor-icons/react';
import Link from 'next/link';
import { useState } from 'react';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import type { AssignmentStatus, AssignmentView } from '@/lib/api/assignments';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './AssignmentCard.module.css';

const STATUS_ICON = {
  DRAFT: CalendarCheck,
  CONFIRMED: CalendarCheck,
  IN_PROGRESS: Timer,
  COMPLETED: CheckCircle,
  EXPIRED: ClockCountdown,
  CANCELLED: Prohibit,
  NO_SHOW: Prohibit,
} satisfies Record<AssignmentStatus, typeof CalendarCheck>;

export interface AssignmentCardProps {
  assignment: AssignmentView;
  onCommand: (assignment: AssignmentView, command: 'start' | 'complete') => Promise<void>;
}

export function AssignmentCard({ assignment, onCommand }: AssignmentCardProps) {
  const { t, formatDateTime } = useLocale();
  const [confirming, setConfirming] = useState<'start' | 'complete' | null>(null);
  const [busy, setBusy] = useState(false);
  const Icon = STATUS_ICON[assignment.status];
  const availableCommand =
    assignment.status === 'CONFIRMED'
      ? 'start'
      : assignment.status === 'IN_PROGRESS'
        ? 'complete'
        : null;

  async function runCommand() {
    if (!confirming) return;
    setBusy(true);
    try {
      await onCommand(assignment, confirming);
      setConfirming(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={styles.card} data-status={assignment.status}>
      <div className={styles.header}>
        <div className={styles.status}>
          <Icon size={22} weight="bold" aria-hidden="true" />
          <span>{t(`assignmentStatus.${assignment.status}` as MessageKey)}</span>
        </div>
        <span className={styles.version}>
          {t('common.version', { version: assignment.version })}
        </span>
      </div>
      <dl className={styles.details}>
        <div>
          <dt>{t('assignments.scheduledStart')}</dt>
          <dd>{formatDateTime(assignment.scheduledStart)}</dd>
        </div>
        <div>
          <dt>{t('assignments.scheduledEnd')}</dt>
          <dd>{formatDateTime(assignment.scheduledEnd)}</dd>
        </div>
        <div>
          <dt>{t('assignments.scopeCount')}</dt>
          <dd>{assignment.scopeCount}</dd>
        </div>
        <div>
          <dt>{t('assignments.expiresAt')}</dt>
          <dd>{formatDateTime(assignment.expiresAt)}</dd>
        </div>
      </dl>
      <div className={styles.actions}>
        <Link className={styles.elderLink} href={`/staff/elders/${assignment.elderId}`}>
          {t('assignments.openElder')}
        </Link>
        {availableCommand && (
          <button
            className={styles.command}
            disabled={busy}
            onClick={() => setConfirming(availableCommand)}
            type="button"
          >
            {t(`assignments.${availableCommand}` as MessageKey)}
          </button>
        )}
      </div>
      <ConfirmationDialog
        busy={busy}
        confirmLabel={
          confirming ? t(`assignments.${confirming}` as MessageKey) : t('common.confirm')
        }
        description={t('assignments.confirmDescription')}
        onCancel={() => setConfirming(null)}
        onConfirm={() => void runCommand()}
        open={confirming !== null}
        title={t('assignments.confirmTitle')}
      />
    </article>
  );
}
