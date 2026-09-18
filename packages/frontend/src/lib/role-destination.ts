/**
 * Where an authenticated actor belongs, by role.
 *
 * One table, used by both the post-sign-in resolver (`app/onboarding/resolve`)
 * and the signed-in home gate (`components/SignedInHome`). A second copy would
 * drift, and the symptom would be a role that lands somewhere it cannot use
 * without anything failing loudly.
 *
 * This decides navigation, never access. Core re-authorizes every read on the
 * destination regardless of how the browser got there, so a wrong answer here
 * costs a wasted hop, not an authorization bypass (AGENTS.md §5).
 */
export interface RoleBearingProfile {
  /** Core returns `role`; some older payload shapes carry `actor_type`. */
  role?: string;
  actor_type?: string;
}

/** The elder's destination. Their companion *is* the home route. */
export const ELDER_HOME = '/';

export function destinationFor(profile: RoleBearingProfile): string | null {
  const role = profile.role ?? profile.actor_type;
  if (role === 'ADMIN') return '/admin';
  if (role === 'ELDER') return ELDER_HOME;
  if (role === 'FAMILY_MEMBER') return '/family';
  if (role === 'DAYCARE_CARE_WORKER' || role === 'HOME_CARE_WORKER') return '/staff';
  // An actor whose role has no surface yet stays put rather than being sent
  // somewhere arbitrary; the caller decides what to say about it.
  return null;
}
