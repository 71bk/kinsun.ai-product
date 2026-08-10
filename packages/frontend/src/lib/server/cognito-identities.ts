import {
  AdminLinkProviderForUserCommand,
  CognitoIdentityProviderClient,
  GetUserCommand,
  type AttributeType,
} from '@aws-sdk/client-cognito-identity-provider';
import { normalizeAccessToken } from './auth-cookie';
import type { VerifiedLineLoginIdentity } from './line-login-oauth';
import {
  lineLoginLinkDestinationMatches,
  type LineLoginLinkTransaction,
} from './line-login-link-transaction';

const MAX_IDENTITIES_ATTRIBUTE_LENGTH = 16_384;

export interface SignInMethodStatus {
  googleLinked: boolean;
  lineLinked: boolean;
}

export interface LineLoginLinkDestination extends SignInMethodStatus {
  /** Server-only input used immediately to derive an HMAC transaction binding. */
  cognitoUsername: string;
}

interface CurrentCognitoUser extends SignInMethodStatus {
  email: string;
  emailVerified: boolean;
  lineSubject?: string;
  username: string;
}

export class CognitoIdentityError extends Error {
  constructor(
    readonly reason:
      | 'AUTHENTICATION_REQUIRED'
      | 'CONFIGURATION_UNAVAILABLE'
      | 'IDENTITY_CONFLICT'
      | 'GOOGLE_REQUIRED'
      | 'LINE_EMAIL_MISMATCH'
      | 'LINK_DESTINATION_CHANGED',
  ) {
    super(reason);
    this.name = 'CognitoIdentityError';
  }
}

function configuration(): { providerName: string; region: string; userPoolId: string } {
  const region = process.env.COGNITO_REGION;
  const userPoolId = process.env.COGNITO_USER_POOL_ID;
  const providerName = process.env.COGNITO_LINE_PROVIDER_NAME ?? 'LINE';
  if (
    !region ||
    !/^[a-z]{2}(?:-gov)?-[a-z]+-\d$/.test(region) ||
    !userPoolId ||
    userPoolId.length > 128 ||
    /\s/.test(userPoolId) ||
    !/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(providerName)
  ) {
    throw new CognitoIdentityError('CONFIGURATION_UNAVAILABLE');
  }
  return { providerName, region, userPoolId };
}

function attribute(attributes: AttributeType[] | undefined, name: string): string | null {
  const values = attributes?.filter((entry) => entry.Name === name) ?? [];
  if (values.length !== 1 || typeof values[0]?.Value !== 'string') return null;
  const value = values[0].Value.trim();
  return value || null;
}

function normalizedEmail(value: string | null): string | null {
  if (!value) return null;
  const email = value.trim().toLowerCase();
  return email && email.length <= 320 && email.includes('@') && !/\s/.test(email) ? email : null;
}

function linkedIdentities(
  attributes: AttributeType[] | undefined,
): Array<{ providerName: string; userId: string }> {
  const raw = attribute(attributes, 'identities');
  if (!raw || raw.length > MAX_IDENTITIES_ATTRIBUTE_LENGTH) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed) || parsed.length > 10) return [];
    return parsed.flatMap((entry) => {
      if (!entry || typeof entry !== 'object') return [];
      const providerName = (entry as { providerName?: unknown }).providerName;
      const userId = (entry as { userId?: unknown }).userId;
      return typeof providerName === 'string' &&
        providerName.length <= 64 &&
        typeof userId === 'string' &&
        userId.length <= 255
        ? [{ providerName, userId }]
        : [];
    });
  } catch {
    return [];
  }
}

async function currentUser(
  client: CognitoIdentityProviderClient,
  accessToken: string,
  lineProviderName: string,
): Promise<CurrentCognitoUser> {
  try {
    const result = await client.send(new GetUserCommand({ AccessToken: accessToken }));
    if (!result.Username || result.Username.length > 256 || /\s/.test(result.Username)) {
      throw new CognitoIdentityError('AUTHENTICATION_REQUIRED');
    }
    const identities = linkedIdentities(result.UserAttributes);
    const googleIdentity = identities.find(
      (identity) => identity.providerName.toLowerCase() === 'google',
    );
    const lineIdentity = identities.find(
      (identity) => identity.providerName.toLowerCase() === lineProviderName.toLowerCase(),
    );
    const email = normalizedEmail(attribute(result.UserAttributes, 'email'));
    if (!email) throw new CognitoIdentityError('AUTHENTICATION_REQUIRED');
    return {
      username: result.Username,
      email,
      emailVerified: attribute(result.UserAttributes, 'email_verified') === 'true',
      googleLinked: Boolean(googleIdentity) || result.Username.toLowerCase().startsWith('google_'),
      lineLinked: Boolean(lineIdentity),
      ...(lineIdentity ? { lineSubject: lineIdentity.userId } : {}),
    };
  } catch (error) {
    if (error instanceof CognitoIdentityError) throw error;
    throw new CognitoIdentityError('AUTHENTICATION_REQUIRED');
  }
}

function clientForRegion(region: string): CognitoIdentityProviderClient {
  return new CognitoIdentityProviderClient({ region });
}

export async function getSignInMethodStatus(rawAccessToken: unknown): Promise<SignInMethodStatus> {
  const destination = await getLineLoginLinkDestination(rawAccessToken);
  return {
    googleLinked: destination.googleLinked,
    lineLinked: destination.lineLinked,
  };
}

export async function getLineLoginLinkDestination(
  rawAccessToken: unknown,
): Promise<LineLoginLinkDestination> {
  const accessToken = normalizeAccessToken(rawAccessToken);
  if (!accessToken) throw new CognitoIdentityError('AUTHENTICATION_REQUIRED');
  const config = configuration();
  const user = await currentUser(clientForRegion(config.region), accessToken, config.providerName);
  return {
    cognitoUsername: user.username,
    googleLinked: user.googleLinked,
    lineLinked: user.lineLinked,
  };
}

export async function linkLineLoginIdentity(
  rawAccessToken: unknown,
  lineIdentity: VerifiedLineLoginIdentity,
  transaction: LineLoginLinkTransaction,
): Promise<'LINKED' | 'ALREADY_LINKED'> {
  const accessToken = normalizeAccessToken(rawAccessToken);
  if (!accessToken) throw new CognitoIdentityError('AUTHENTICATION_REQUIRED');
  const config = configuration();
  const client = clientForRegion(config.region);
  const user = await currentUser(client, accessToken, config.providerName);
  if (!lineLoginLinkDestinationMatches(transaction, user.username)) {
    throw new CognitoIdentityError('LINK_DESTINATION_CHANGED');
  }
  if (!user.googleLinked) throw new CognitoIdentityError('GOOGLE_REQUIRED');
  if (!user.emailVerified) throw new CognitoIdentityError('AUTHENTICATION_REQUIRED');
  if (user.email !== lineIdentity.email) {
    // Email is never used to find or merge an Actor. This equality guard only
    // prevents Cognito's required OIDC email mapping from overwriting the
    // already-authenticated destination user's recovery address.
    throw new CognitoIdentityError('LINE_EMAIL_MISMATCH');
  }
  if (user.lineLinked) {
    if (user.lineSubject === lineIdentity.subject) return 'ALREADY_LINKED';
    throw new CognitoIdentityError('IDENTITY_CONFLICT');
  }

  try {
    await client.send(
      new AdminLinkProviderForUserCommand({
        UserPoolId: config.userPoolId,
        DestinationUser: {
          ProviderName: 'Cognito',
          ProviderAttributeValue: user.username,
        },
        SourceUser: {
          ProviderName: config.providerName,
          ProviderAttributeName: 'Cognito_Subject',
          ProviderAttributeValue: lineIdentity.subject,
        },
      }),
    );
    return 'LINKED';
  } catch (error) {
    const name = error instanceof Error ? error.name : '';
    if (
      name === 'AliasExistsException' ||
      name === 'InvalidParameterException' ||
      name === 'ResourceNotFoundException'
    ) {
      throw new CognitoIdentityError('IDENTITY_CONFLICT');
    }
    if (name === 'NotAuthorizedException') {
      throw new CognitoIdentityError('AUTHENTICATION_REQUIRED');
    }
    throw new CognitoIdentityError('CONFIGURATION_UNAVAILABLE');
  }
}
