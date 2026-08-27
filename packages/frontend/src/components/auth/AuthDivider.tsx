export function AuthDivider({ label }: { label: string }) {
  return (
    <div
      role="separator"
      style={{
        alignItems: 'center',
        color: 'var(--color-muted-foreground)',
        display: 'flex',
        fontSize: 'var(--text-sm)',
        gap: 'var(--space-3)',
        margin: 'var(--space-6) 0',
      }}
    >
      <span aria-hidden="true" style={{ background: 'var(--color-border-strong)', flex: 1, height: 1 }} />
      {label}
      <span aria-hidden="true" style={{ background: 'var(--color-border-strong)', flex: 1, height: 1 }} />
    </div>
  );
}
