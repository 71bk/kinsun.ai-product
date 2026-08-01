import * as cdk from 'aws-cdk-lib';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

export interface SecurityStackProps extends cdk.StackProps {
  vpc: ec2.IVpc;
}

export class SecurityStack extends cdk.Stack {
  public readonly dataKey: kms.IKey;
  public readonly userPool: cognito.IUserPool;

  constructor(scope: Construct, id: string, props: SecurityStackProps) {
    super(scope, id, props);

    // KMS key for data encryption
    this.dataKey = new kms.Key(this, 'DataKey', {
      alias: `${this.stackName}-data`,
      enableKeyRotation: true,
      description: 'Encryption key for elderly care system data',
    });

    // Cognito User Pool with Google + LINE federation
    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: `${this.stackName}-users`,
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      mfa: cognito.Mfa.OPTIONAL,
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // Google Identity Provider (configure client ID/secret via env)
    // LINE Identity Provider (configure via OIDC)
    // TODO: Add Google/LINE federation after obtaining OAuth credentials

    const client = new cognito.UserPoolClient(this, 'AppClient', {
      userPool: this.userPool as cognito.UserPool,
      authFlows: { userSrp: true },
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
        callbackUrls: ['http://localhost:3000/api/auth/callback'],
        logoutUrls: ['http://localhost:3000/'],
      },
    });

    new cdk.CfnOutput(this, 'UserPoolId', { value: this.userPool.userPoolId });
    new cdk.CfnOutput(this, 'UserPoolClientId', { value: client.userPoolClientId });
  }
}
