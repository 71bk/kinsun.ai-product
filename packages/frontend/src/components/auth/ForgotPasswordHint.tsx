/**
 * "Forgot password?" has no backing flow yet — core-api exposes no
 * reset-password endpoint. Rendered as static, muted text (not a link or
 * disabled button) so it never reads as a tappable control that silently
 * does nothing.
 */
export function ForgotPasswordHint({ label, hint }: { label: string; hint: string }) {
  return (
    <span style={{ color: 'var(--color-muted-foreground)', fontSize: 'var(--text-sm)' }}>
      {label}
      <span style={{ marginInlineStart: 'var(--space-1)' }}>（{hint}）</span>
    </span>
  );
}
