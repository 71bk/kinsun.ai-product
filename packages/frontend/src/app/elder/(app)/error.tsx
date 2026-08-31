'use client';

import { RouteErrorBoundary } from '@/components/ui/RouteErrorBoundary';

/**
 * Elder surface boundary.
 *
 * Newly possible: before `elder/(app)/layout.tsx` existed there was no shell to
 * stay inside, so a throw here fell all the way to the root boundary and the
 * elder lost the navigation back to 陪我聊天, 我的記憶 and 同意設定. Now the
 * failure keeps the shell around it.
 *
 * `RouteErrorBoundary` is safe here because `ElderShell` provides a
 * `LocaleProvider` (pinned to zh-Hant — the voice surface has no language
 * switch, MASTER.md §5.2), which is what `ErrorState` needs.
 */
export default function ElderError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteErrorBoundary error={error} reset={reset} scope="elder" />;
}
