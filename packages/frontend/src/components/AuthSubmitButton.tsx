'use client';

import type { ReactNode } from 'react';

/**
 * The "continue with Google" submit button, shared by every sign-in entry point.
 *
 * It exists because two of the three copies were a bare <button> with no styles
 * at all, rendering 23px tall — half of MASTER.md §6.1's 48px floor, on the
 * screens where a family member or care worker first arrives. A fourth
 * hand-rolled copy would have drifted the same way.
 *
 * The fill is --color-primary-strong rather than --color-primary: the label sits
 * below 24px, so it needs the 4.5:1 body-text ratio, and white on
 * --color-primary is only 3.68:1 (§4.1, §13).
 */
export function AuthSubmitButton({
  children,
  disabled = false,
  pending = false,
  pendingLabel = '處理中…',
}: {
  children: ReactNode;
  disabled?: boolean;
  pending?: boolean;
  pendingLabel?: ReactNode;
}) {
  const isDisabled = disabled || pending;

  return (
    <button
      aria-busy={pending}
      aria-live="polite"
      disabled={isDisabled}
      type="submit"
      style={{
        background: 'var(--color-primary-strong)',
        border: 0,
        borderRadius: 'var(--radius-md)',
        color: 'var(--color-on-primary)',
        cursor: pending ? 'wait' : disabled ? 'not-allowed' : 'pointer',
        fontFamily: 'inherit',
        fontSize: 'var(--text-base)',
        // Height comes from min-height so a 200% system font size grows the
        // control instead of clipping the label (§5.1).
        minHeight: 'var(--touch-min)',
        opacity: isDisabled ? 0.72 : 1,
        padding: 'var(--space-3) var(--space-6)',
      }}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
