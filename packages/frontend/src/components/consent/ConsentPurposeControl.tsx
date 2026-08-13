'use client';

import { CheckCircle, Circle } from '@phosphor-icons/react';
import { useState, type ReactNode } from 'react';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { ApiRequestError } from '@/lib/api/client';
import type { ConsentRecord } from '@/lib/api/consent';
import styles from './ConsentPurposeControl.module.css';

export interface ConsentPurposeControlProps {
  title: string;
  description: string;
  details: string[];
  icon: ReactNode;
  initialConsent: ConsentRecord | null;
  policyVersion: string;
  grantLabel: string;
  revokeLabel: string;
  grantConfirmation: string;
  revokeConfirmation: string;
  onGrant: () => Promise<ConsentRecord>;
  onRevoke: (consent: ConsentRecord) => Promise<ConsentRecord>;
  onChange: (consent: ConsentRecord | null) => void;
}

function describeConsentError(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 404) {
    return '目前無法設定這項同意，請確認登入身分與長者範圍。';
  }
  if (error instanceof ApiRequestError && error.status === 409) {
    return '同意狀態剛剛已變更，請重新整理後再試。';
  }
  return '設定沒有完成，請稍後再試。';
}

export function ConsentPurposeControl({
  title,
  description,
  details,
  icon,
  initialConsent,
  policyVersion,
  grantLabel,
  revokeLabel,
  grantConfirmation,
  revokeConfirmation,
  onGrant,
  onRevoke,
  onChange,
}: ConsentPurposeControlProps) {
  const [consent, setConsent] = useState(initialConsent);
  const [pending, setPending] = useState<'grant' | 'revoke' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = consent !== null;

  async function confirmChange() {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      if (pending === 'grant') {
        const next = await onGrant();
        setConsent(next);
        onChange(next);
      } else if (consent) {
        await onRevoke(consent);
        setConsent(null);
        onChange(null);
      }
      setPending(null);
    } catch (caught) {
      setError(describeConsentError(caught));
      setPending(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={styles.card} data-active={active}>
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden="true">
          {icon}
        </span>
        <div>
          <h2>{title}</h2>
          <span className={styles.status}>
            {active ? (
              <CheckCircle aria-hidden="true" size={26} weight="fill" />
            ) : (
              <Circle aria-hidden="true" size={26} />
            )}
            {active ? '已開啟' : '未開啟'}
          </span>
        </div>
      </div>
      <p className={styles.description}>{description}</p>
      <ul className={styles.details}>
        {details.map((detail) => (
          <li key={detail}>{detail}</li>
        ))}
      </ul>
      {active && <p className={styles.version}>Core 同意版本 {consent.consent_version}</p>}
      {!active && !policyVersion && (
        <p className={styles.error} role="alert">
          尚未設定同意政策版本，目前不能開啟這項用途。
        </p>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      <button
        className={active ? styles.revoke : styles.grant}
        disabled={busy || (!active && !policyVersion)}
        onClick={() => setPending(active ? 'revoke' : 'grant')}
        type="button"
      >
        {active ? revokeLabel : grantLabel}
      </button>
      <ConfirmationDialog
        busy={busy}
        confirmLabel={pending === 'revoke' ? revokeLabel : grantLabel}
        description={pending === 'revoke' ? revokeConfirmation : grantConfirmation}
        onCancel={() => setPending(null)}
        onConfirm={() => void confirmChange()}
        open={pending !== null}
        title={pending === 'revoke' ? `確認${revokeLabel}？` : `確認${grantLabel}？`}
        tone={pending === 'revoke' ? 'destructive' : 'default'}
      />
    </article>
  );
}
