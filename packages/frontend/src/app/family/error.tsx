'use client';

import { RouteErrorBoundary } from '@/components/ui/RouteErrorBoundary';

/**
 * Family surface boundary.
 *
 * Placed at /family rather than /family/(app) so it also covers sign-in and
 * join, and so it renders inside `family/layout.tsx` — keeping the SurfaceShell
 * header, the family token scale and the language switch instead of dropping to
 * Next's bare default page.
 *
 * This is the boundary MASTER.md §11 assumes exists: `listFamilyReports` throws
 * `FamilyDataRedlineError` on a redline violation precisely so the whole page
 * fails, and until now that failure had nothing to land on.
 */
export default function FamilyError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteErrorBoundary error={error} reset={reset} scope="family" />;
}
