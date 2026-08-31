import type { ReactNode } from 'react';
import { ElderShell } from '@/components/elder/ElderShell';

/**
 * Owns the voice surface for the authenticated elder destinations.
 *
 * Until now every elder page imported `ElderShell` itself, and `/elder/start`
 * set `data-surface="voice"` by hand — three separate ways to reach the same
 * scope, so a new page that forgot all three would silently render without the
 * 640px measure, the 64px targets (MASTER.md §6.1) and the thicker focus ring,
 * with nothing failing to say so.
 *
 * `/elder/start` stays outside this group deliberately, mirroring
 * `family/(app)`: the shell carries sign-out and links to memories and consent,
 * none of which mean anything before the visitor is signed in.
 */
export default function ElderAppLayout({ children }: { children: ReactNode }) {
  return <ElderShell>{children}</ElderShell>;
}
