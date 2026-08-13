'use client';

import { useEffect, useId, useRef, type ReactNode } from 'react';
import { useLocale } from '@/lib/i18n/locale-context';
import styles from './ConfirmationDialog.module.css';

export interface ConfirmationDialogProps {
  open: boolean;
  title: ReactNode;
  description: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'default' | 'destructive';
  busy?: boolean;
}

/**
 * Native modal confirmation with keyboard focus containment and Escape support.
 * It is UI plumbing only; callers remain responsible for invoking an existing
 * authorized workflow and for showing version conflicts or server rejection.
 */
export function ConfirmationDialog({
  open,
  title,
  description,
  onConfirm,
  onCancel,
  confirmLabel,
  cancelLabel,
  tone = 'default',
  busy = false,
}: ConfirmationDialogProps) {
  const { t } = useLocale();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
      cancelRef.current?.focus();
      return;
    }

    if (!open && dialog.open) {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
    }
  }, [open]);

  const requestCancel = () => {
    if (!busy) onCancel();
  };

  return (
    <dialog
      aria-busy={busy}
      aria-describedby={descriptionId}
      aria-labelledby={titleId}
      aria-modal="true"
      className={styles.dialog}
      onCancel={(event) => {
        event.preventDefault();
        requestCancel();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) requestCancel();
      }}
      ref={dialogRef}
    >
      <form
        className={styles.panel}
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy) onConfirm();
        }}
      >
        <h2 className={styles.title} id={titleId}>
          {title}
        </h2>
        <div className={styles.description} id={descriptionId}>
          {description}
        </div>
        <div className={styles.actions} data-tone={tone}>
          <button
            className={styles.cancel}
            disabled={busy}
            onClick={requestCancel}
            ref={cancelRef}
            type="button"
          >
            {cancelLabel ?? t('common.cancel')}
          </button>
          <button className={styles.confirm} data-tone={tone} disabled={busy} type="submit">
            {confirmLabel ?? t('common.confirm')}
          </button>
        </div>
      </form>
    </dialog>
  );
}
