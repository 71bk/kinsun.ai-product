import type { ReactNode } from 'react';
import { FamilyNav } from '@/components/family/FamilyNav';

/**
 * Scoped to the authenticated family destinations only. `/family/join` and
 * `/family/sign-in` sit outside this route group (Stitch plan §2.1 marks them
 * "保留") and stay on the parent `family/layout.tsx`, which only provides
 * `SurfaceShell` — showing Home/Reports nav before the elder relationship is
 * established would be premature.
 */
export default function FamilyAppLayout({ children }: { children: ReactNode }) {
  return <FamilyNav>{children}</FamilyNav>;
}
