export interface RuntimeConfig {
  apiBaseUrl: string;
  wsUrl: string;
  token: string;
  elderId: string;
}

/**
 * Reads the values the voice UI needs to talk to the backend. Cognito
 * sign-in (Hosted UI / Amplify) isn't part of this task list — until it's
 * wired in, the ID token and elderId are expected in localStorage (set by
 * whatever auth flow eventually replaces this) or NEXT_PUBLIC_* env vars
 * for local demo/dev use. This is intentionally the one seam a real auth
 * integration should replace, rather than something scattered across
 * components.
 */
export function getRuntimeConfig(): RuntimeConfig {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? '';

  if (typeof window === 'undefined') {
    return { apiBaseUrl, wsUrl, token: '', elderId: '' };
  }

  const token = window.localStorage.getItem('elderly_care_id_token') ?? '';
  const elderId = window.localStorage.getItem('elderly_care_elder_id') ?? '';
  return { apiBaseUrl, wsUrl, token, elderId };
}
