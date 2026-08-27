'use client';

import { GoogleLogo } from '@phosphor-icons/react';
import type { ReactNode } from 'react';

const oauthButtonStyle = {
  alignItems: 'center',
  background: 'var(--color-surface)',
  border: '2px solid var(--color-interactive-border)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-foreground)',
  cursor: 'pointer',
  display: 'flex',
  fontFamily: 'inherit',
  fontSize: 'var(--text-base)',
  gap: 'var(--space-3)',
  justifyContent: 'center',
  minHeight: 'var(--touch-min)',
  padding: 'var(--space-3) var(--space-5)',
  width: '100%',
};

function OAuthButton({ children }: { children: ReactNode }) {
  return (
    <button style={oauthButtonStyle} type="submit">
      {children}
    </button>
  );
}

export function GoogleContinueButton({ label }: { label: string }) {
  return (
    <OAuthButton>
      <GoogleLogo aria-hidden="true" size={22} weight="bold" />
      <span>{label}</span>
    </OAuthButton>
  );
}

/**
 * No official LINE mark ships in the icon set the project standardized on
 * (`@phosphor-icons/react`), and MASTER.md's icon rules require correct brand
 * assets or none at all — so this stays text-only rather than guessing at one.
 */
export function LineContinueButton({ label }: { label: string }) {
  return (
    <OAuthButton>
      <span>{label}</span>
    </OAuthButton>
  );
}
