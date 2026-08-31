'use client';

import { RouteErrorBoundary } from '@/components/ui/RouteErrorBoundary';

/**
 * Care surface boundary.
 *
 * Renders inside `dashboard/layout.tsx`, so the caregiver keeps the SurfaceShell
 * frame and the care token scale rather than being dropped onto Next's default
 * page mid-shift.
 *
 * §10.2 requires that a permission failure show neither the elder's name nor
 * any other sensitive content; `RouteErrorBoundary` never renders the error, so
 * that holds whatever the throw site happened to include.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteErrorBoundary error={error} reset={reset} scope="dashboard" />;
}
