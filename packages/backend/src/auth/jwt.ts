import { CognitoJwtVerifier } from 'aws-jwt-verify';
import type { UserRole } from '@elderly-care/shared';

export interface VerifiedIdentity {
  userId: string;
  role: UserRole;
  tenantId: string;
}

const ROLE_GROUPS: readonly UserRole[] = ['elder', 'caregiver', 'family', 'admin'];

/** Maps a Cognito group name (case-insensitive: "Elder", "Caregiver", ...) to a UserRole. */
export function mapCognitoGroupToRole(groups: string[]): UserRole | null {
  for (const group of groups) {
    const match = ROLE_GROUPS.find((role) => role === group.toLowerCase());
    if (match) return match;
  }
  return null;
}

let cachedVerifier: ReturnType<typeof CognitoJwtVerifier.create> | null = null;

function getVerifier() {
  if (!cachedVerifier) {
    const userPoolId = process.env.COGNITO_USER_POOL_ID;
    const clientId = process.env.COGNITO_CLIENT_ID;
    if (!userPoolId || !clientId) {
      throw new Error('COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID must be set to verify JWTs');
    }
    cachedVerifier = CognitoJwtVerifier.create({
      userPoolId,
      tokenUse: 'id',
      clientId,
    });
  }
  return cachedVerifier;
}

/**
 * Verifies a Cognito ID token and extracts the identity used to build an
 * AuthorizationContext. Throws if the token is invalid, expired, or carries
 * no recognizable role group — callers (the Lambda Authorizer) treat any
 * throw as Deny.
 */
export async function verifyIdToken(token: string): Promise<VerifiedIdentity> {
  const verifier = getVerifier();
  const payload = await verifier.verify(token);

  const groups = (payload['cognito:groups'] as string[] | undefined) ?? [];
  const role = mapCognitoGroupToRole(groups);
  if (!role) {
    throw new Error('Token carries no recognized role group');
  }

  const tenantId = (payload['custom:tenantId'] as string | undefined) ?? 'default';

  return { userId: payload.sub, role, tenantId };
}
