import * as cdk from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';

export interface GoogleFederationProps {
  /** Google Web OAuth client ID. This value is not secret. */
  readonly clientId: string;
  /** Resolve this from Secrets Manager; never pass or output plaintext. */
  readonly clientSecret: cdk.SecretValue;
  /** Globally unique prefix for the Cognito managed-login domain. */
  readonly domainPrefix: string;
  /** Exact application callback URLs registered for this staging client. */
  readonly callbackUrls: readonly string[];
  /** Exact post-logout URLs registered for this staging client. */
  readonly logoutUrls: readonly string[];
}

export interface LineLoginFederationProps {
  /** LINE Login Channel ID. This value is not secret. */
  readonly channelId: string;
  /** Resolve this from Secrets Manager; never pass or output plaintext. */
  readonly channelSecret: cdk.SecretValue;
  /** Existing same-account role assumed by the deployed Next.js BFF. */
  readonly bffExecutionRoleArn: string;
  /** Cognito custom OIDC provider name. Defaults to LINE. */
  readonly providerName?: string;
}

export interface AuthProps {
  readonly envName: string;
  /** Optional during the parent-stack migration. */
  readonly googleFederation?: GoogleFederationProps;
  /** Requires Google federation because LINE may only be linked to an existing Google user. */
  readonly lineLoginFederation?: LineLoginFederationProps;
}

/** Cognito User Pool with one group per role (H01) — Elder/Caregiver/Family/Admin. */
export class Auth extends Construct {
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;
  public readonly identityPool: cognito.CfnIdentityPool;
  public readonly googleIdentityProvider?: cognito.UserPoolIdentityProviderGoogle;
  public readonly lineLoginIdentityProvider?: cognito.UserPoolIdentityProviderOidc;
  public readonly lineLoginProviderName?: string;
  public readonly userPoolDomain?: cognito.UserPoolDomain;
  public readonly webBffClient?: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: AuthProps) {
    super(scope, id);

    if ((props.googleFederation || props.lineLoginFederation) && props.envName !== 'staging') {
      throw new Error('Login federation is enabled only for the staging environment');
    }
    if (props.lineLoginFederation && !props.googleFederation) {
      throw new Error('LINE Login federation requires Google federation');
    }

    const lineProviderName = props.lineLoginFederation?.providerName ?? 'LINE';
    if (
      props.lineLoginFederation &&
      (!/^\d{5,32}$/.test(props.lineLoginFederation.channelId) ||
        !/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(lineProviderName) ||
        (!cdk.Token.isUnresolved(props.lineLoginFederation.bffExecutionRoleArn) &&
          !/^arn:[^:\s]+:iam::\d{12}:role\/[A-Za-z0-9_+=,.@\/-]{1,512}$/.test(
            props.lineLoginFederation.bffExecutionRoleArn,
          )))
    ) {
      throw new Error('Invalid LINE Login federation settings');
    }
    this.lineLoginProviderName = props.lineLoginFederation ? lineProviderName : undefined;

    const linePreSignUpGuard = props.lineLoginFederation
      ? new lambda.Function(this, 'LinePreSignUpGuard', {
          runtime: lambda.Runtime.NODEJS_22_X,
          handler: 'index.handler',
          code: lambda.Code.fromInline(`
exports.handler = async (event) => {
  const userName = typeof event.userName === 'string' ? event.userName.toLowerCase() : '';
  const prefix = (process.env.LINE_PROVIDER_PREFIX || '').toLowerCase();
  if (event.triggerSource === 'PreSignUp_ExternalProvider' && prefix && userName.startsWith(prefix)) {
    throw new Error('LINE Login must be linked from an existing account');
  }
  return event;
};
`),
          environment: { LINE_PROVIDER_PREFIX: `${lineProviderName}_` },
          description: 'Deny creation of unlinked LINE federated Cognito users',
          timeout: cdk.Duration.seconds(5),
        })
      : undefined;

    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: `elderly-care-users-${props.envName}`,
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      standardAttributes: {
        email: { required: true, mutable: true },
      },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      lambdaTriggers: linePreSignUpGuard ? { preSignUp: linePreSignUpGuard } : undefined,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    if (props.lineLoginFederation) {
      const bffExecutionRole = iam.Role.fromRoleArn(
        this,
        'LineLinkBffExecutionRole',
        props.lineLoginFederation.bffExecutionRoleArn,
        { mutable: true },
      );
      bffExecutionRole.addToPrincipalPolicy(
        new iam.PolicyStatement({
          actions: ['cognito-idp:AdminLinkProviderForUser'],
          resources: [this.userPool.userPoolArn],
        }),
      );
    }

    this.userPoolClient = new cognito.UserPoolClient(this, 'UserPoolClient', {
      userPool: this.userPool,
      authFlows: { userSrp: true },
      generateSecret: false,
      accessTokenValidity: cdk.Duration.hours(1),
      idTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
    });

    if (props.googleFederation) {
      const federation = props.googleFederation;
      if (federation.callbackUrls.length === 0 || federation.logoutUrls.length === 0) {
        throw new Error('Google federation requires callback and logout URLs');
      }

      this.googleIdentityProvider = new cognito.UserPoolIdentityProviderGoogle(
        this,
        'GoogleIdentityProvider',
        {
          userPool: this.userPool,
          clientId: federation.clientId,
          clientSecretValue: federation.clientSecret,
          scopes: ['openid', 'email', 'profile'],
          attributeMapping: {
            email: cognito.ProviderAttribute.GOOGLE_EMAIL,
            emailVerified: cognito.ProviderAttribute.GOOGLE_EMAIL_VERIFIED,
            fullname: cognito.ProviderAttribute.GOOGLE_NAME,
            givenName: cognito.ProviderAttribute.GOOGLE_GIVEN_NAME,
            familyName: cognito.ProviderAttribute.GOOGLE_FAMILY_NAME,
            profilePicture: cognito.ProviderAttribute.GOOGLE_PICTURE,
          },
        },
      );

      if (props.lineLoginFederation) {
        const line = props.lineLoginFederation;
        this.lineLoginIdentityProvider = new cognito.UserPoolIdentityProviderOidc(
          this,
          'LineLoginIdentityProvider',
          {
            userPool: this.userPool,
            clientId: line.channelId,
            clientSecret: line.channelSecret.unsafeUnwrap(),
            issuerUrl: 'https://access.line.me',
            name: lineProviderName,
            scopes: ['openid', 'profile', 'email'],
            attributeMapping: {
              email: cognito.ProviderAttribute.other('email'),
              fullname: cognito.ProviderAttribute.other('name'),
              profilePicture: cognito.ProviderAttribute.other('picture'),
            },
          },
        );
      }

      this.userPoolDomain = this.userPool.addDomain('ManagedLoginDomain', {
        cognitoDomain: { domainPrefix: federation.domainPrefix },
      });

      const supportedIdentityProviders = [cognito.UserPoolClientIdentityProvider.GOOGLE];
      if (props.lineLoginFederation) {
        supportedIdentityProviders.push(
          cognito.UserPoolClientIdentityProvider.custom(lineProviderName),
        );
      }
      this.webBffClient = new cognito.UserPoolClient(this, 'WebBffClient', {
        userPool: this.userPool,
        userPoolClientName: `elderly-care-web-bff-${props.envName}`,
        // Public authorization-code client: the caller must use PKCE S256.
        generateSecret: false,
        supportedIdentityProviders,
        oAuth: {
          flows: {
            authorizationCodeGrant: true,
            implicitCodeGrant: false,
            clientCredentials: false,
          },
          scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
          callbackUrls: [...federation.callbackUrls],
          logoutUrls: [...federation.logoutUrls],
        },
        accessTokenValidity: cdk.Duration.hours(1),
        idTokenValidity: cdk.Duration.hours(1),
        refreshTokenValidity: cdk.Duration.days(30),
        enableTokenRevocation: true,
        refreshTokenRotationGracePeriod: cdk.Duration.seconds(10),
        preventUserExistenceErrors: true,
      });

      // CloudFormation otherwise has no reference from an app client's static
      // SupportedIdentityProviders value to providers or the managed-login domain.
      this.webBffClient.node.addDependency(this.googleIdentityProvider);
      if (this.lineLoginIdentityProvider) {
        this.webBffClient.node.addDependency(this.lineLoginIdentityProvider);
      }
      this.webBffClient.node.addDependency(this.userPoolDomain);
    }

    // One group per UserRole (packages/shared/src/types/enums.ts) — the Lambda
    // Authorizer maps `cognito:groups` to AuthorizationContext.role.
    (['Elder', 'Caregiver', 'Family', 'Admin'] as const).forEach((role, index) => {
      new cognito.CfnUserPoolGroup(this, `${role}Group`, {
        userPoolId: this.userPool.userPoolId,
        groupName: role,
        precedence: index,
      });
    });

    this.identityPool = new cognito.CfnIdentityPool(this, 'IdentityPool', {
      identityPoolName: `elderly_care_identity_${props.envName}`,
      allowUnauthenticatedIdentities: false,
      cognitoIdentityProviders: [
        {
          clientId: this.userPoolClient.userPoolClientId,
          providerName: this.userPool.userPoolProviderName,
        },
      ],
    });
  }
}
