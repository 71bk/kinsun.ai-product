'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { VoiceHomeClient } from '@/components/voice/VoiceHomeClient';
import { apiFetch } from '@/lib/api/client';
import { destinationFor, ELDER_HOME, type RoleBearingProfile } from '@/lib/role-destination';

/**
 * `/` for a visitor carrying a session cookie.
 *
 * `/` is the elder's home screen, so the companion renders immediately and the
 * role lookup runs beside it rather than in front of it. Blocking the render on
 * a Core round trip would tax the one user who is always in the right place, to
 * spare three who are occasionally in the wrong one — and the elder surface is
 * the last place to add a wait (MASTER.md §5.1).
 *
 * Everyone else is moved to their own surface. Without this they reach one of
 * two dead ends: `VoiceHomeClient` shows "尚未設定本機 Demo 身分" when there is no
 * elder id in this browser, or — on a shared tablet still holding a previous
 * elder id — the elder companion itself. The voice surface offers no navigation
 * out of either, so the only escape was signing out.
 *
 * Navigation only. Core re-authorizes every read on the destination, so a
 * misread role costs a wasted hop, never access (AGENTS.md §5).
 */
export function SignedInHome() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    void apiFetch<RoleBearingProfile>({ apiBaseUrl: '/backend/core' }, '/api/v1/me')
      .then((profile) => {
        if (cancelled) return;
        const destination = destinationFor(profile);
        // `null` is a role with no surface yet, and ELDER_HOME is already here.
        // Both stay put: the companion below reports its own state, and that is
        // a better message than bouncing someone somewhere equally unusable.
        if (destination && destination !== ELDER_HOME) router.replace(destination);
      })
      // A failed lookup must not strand anyone on a blank screen. Staying shows
      // the companion, which reports an invalid session on its own.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [router]);

  return <VoiceHomeClient />;
}
