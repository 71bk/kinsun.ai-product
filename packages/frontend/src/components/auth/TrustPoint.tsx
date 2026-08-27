import { Check } from '@phosphor-icons/react';
import type { ReactNode } from 'react';

/**
 * One checklist line in a sign-in hero panel ("重要記憶，確認後才保存" etc.).
 * `tone="onDark"` is for the elder split-screen's dark brand panel; the
 * default tone is for the light card background family/staff sign-in use.
 */
export function TrustPoint({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'onDark' }) {
  return (
    <li
      style={{
        alignItems: 'flex-start',
        color: tone === 'onDark' ? 'var(--color-on-primary)' : 'var(--color-foreground)',
        display: 'flex',
        gap: 'var(--space-2)',
        listStyle: 'none',
        marginTop: 'var(--space-3)',
      }}
    >
      <Check
        aria-hidden="true"
        color={tone === 'onDark' ? 'var(--color-on-primary)' : 'var(--color-accent-text)'}
        size={20}
        style={{ flexShrink: 0, marginTop: 2 }}
        weight="bold"
      />
      <span>{children}</span>
    </li>
  );
}
