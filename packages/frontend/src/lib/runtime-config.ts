import { hasAuthCredential } from './auth-session';
import type { ApiConfig } from './api/client';

export interface RuntimeConfig extends ApiConfig {
  apiBaseUrl: string;
  elderId: string;
  caregiverId: string;
  consentPolicyVersion: string;
  credentialStatus: 'present' | 'missing' | 'unavailable';
}

/**
 * Elder/caregiver IDs select a resource; they are not trusted credentials.
 * Core reauthorizes their scope on every request. Authentication tokens never
 * appear here and are never readable by browser JavaScript.
 */
export const AUTH_STORAGE_KEYS = {
  elderId: 'elderly_care_elder_id',
  caregiverId: 'elderly_care_caregiver_id',
} as const;

/**
 * Everything sign-out has to remove from the browser itself.
 *
 * `POST /backend/auth/logout` runs on the server, so it can only expire the
 * HttpOnly cookies. Without this, signing out left the previous session's elder
 * and caregiver ids behind. The deployment target can be a shared tablet in a
 * care setting, so the next person must never inherit the last person's scope.
 *
 * Safe to call when already signed out; `removeItem` on a missing key is a no-op.
 */
export function clearBrowserSessionState(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(AUTH_STORAGE_KEYS.elderId);
  window.localStorage.removeItem(AUTH_STORAGE_KEYS.caregiverId);
}

/**
 * Reads non-secret target IDs locally, then asks the same-origin BFF whether
 * an HttpOnly credential cookie exists. Presence is not proof that the token
 * is valid; Core remains the authentication and authorization authority.
 */
export async function getRuntimeConfig(): Promise<RuntimeConfig> {
  const apiBaseUrl = '/backend/core';
  const consentPolicyVersion = process.env.NEXT_PUBLIC_CONSENT_POLICY_VERSION ?? '';

  if (typeof window === 'undefined') {
    return {
      apiBaseUrl,
      elderId: '',
      caregiverId: '',
      consentPolicyVersion,
      credentialStatus: 'unavailable',
    };
  }

  const elderId = window.localStorage.getItem(AUTH_STORAGE_KEYS.elderId) ?? '';
  const caregiverId = window.localStorage.getItem(AUTH_STORAGE_KEYS.caregiverId) ?? '';
  let credentialStatus: RuntimeConfig['credentialStatus'] = 'unavailable';
  try {
    credentialStatus = (await hasAuthCredential()) ? 'present' : 'missing';
  } catch {
    // Fail closed without claiming that the user is logged out when the BFF
    // itself is unavailable.
  }
  return { apiBaseUrl, elderId, caregiverId, consentPolicyVersion, credentialStatus };
}
