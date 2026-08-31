import type { ReactNode } from 'react';
import { CareSidebar } from '@/components/care/CareSidebar';

/**
 * Scoped to the authenticated care destinations, mirroring `family/(app)`.
 *
 * `/staff/sign-in` sits outside this group and keeps only the parent
 * `staff/layout.tsx`, which provides `SurfaceShell` — offering the elders and
 * assignments nav before there is a session would be premature.
 *
 * The cookie read and `SurfaceShell` used to be duplicated between
 * `staff/layout.tsx` and the old `dashboard/layout.tsx`, which were identical
 * apart from this sidebar. Now the parent owns the surface and this owns the
 * navigation.
 */
export default function StaffAppLayout({ children }: { children: ReactNode }) {
  return <CareSidebar>{children}</CareSidebar>;
}
