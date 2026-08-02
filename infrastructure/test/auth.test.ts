import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';

import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';

import { Auth } from '../lib/constructs/auth';
import { ElderlyCareStack } from '../lib/elderly-care-stack';

const CALLBACK_URL = 'https://staging.kinsun.example/auth/callback';
const LOGOUT_URL = 'https://staging.kinsun.example/signed-out';
const GOOGLE_CLIENT_ID = 'staging-client.apps.googleusercontent.com';
const GOOGLE_SECRET_NAME = 'kinsun/staging/google-oauth';
const LINE_CHANNEL_ID = '1234567890';
const LINE_SECRET_NAME = 'kinsun/staging/line-login';
const LINE_BFF_ROLE_ARN = 'arn:aws:iam::111111111111:role/kinsun-staging-web-bff';

function createTemplate(withFederation: boolean): Template {
  const app = new cdk.App();
  const stack = new cdk.Stack(app, 'AuthTestStack', {
    env: { account: '111111111111', region: 'ap-northeast-1' },
  });

  new Auth(stack, 'Auth', {
    envName: 'staging',
    googleFederation: withFederation
      ? {
          clientId: GOOGLE_CLIENT_ID,
          clientSecret: cdk.SecretValue.secretsManager(GOOGLE_SECRET_NAME, {
            jsonField: 'clientSecret',
          }),
          domainPrefix: 'kinsun-staging-auth-test',
          callbackUrls: [CALLBACK_URL],
          logoutUrls: [LOGOUT_URL],
        }
      : undefined,
    lineLoginFederation: withFederation
      ? {
          channelId: LINE_CHANNEL_ID,
          channelSecret: cdk.SecretValue.secretsManager(LINE_SECRET_NAME),
          bffExecutionRoleArn: LINE_BFF_ROLE_ARN,
          providerName: 'LINE',
        }
      : undefined,
  });

  return Template.fromStack(stack);
}

describe('Auth', () => {
  it('rejects login federation outside staging', () => {
    const app = new cdk.App();
    const stack = new cdk.Stack(app, 'ProductionAuthTestStack');

    assert.throws(
      () =>
        new Auth(stack, 'Auth', {
          envName: 'production',
          googleFederation: {
            clientId: GOOGLE_CLIENT_ID,
            clientSecret: cdk.SecretValue.secretsManager(GOOGLE_SECRET_NAME),
            domainPrefix: 'must-not-be-created',
            callbackUrls: [CALLBACK_URL],
            logoutUrls: [LOGOUT_URL],
          },
          lineLoginFederation: {
            channelId: LINE_CHANNEL_ID,
            channelSecret: cdk.SecretValue.secretsManager(LINE_SECRET_NAME),
            bffExecutionRoleArn: LINE_BFF_ROLE_ARN,
          },
        }),
      /only for the staging environment/,
    );
  });

  it('preserves the legacy client and identity pool when federation is not configured', () => {
    const template = createTemplate(false);

    template.resourceCountIs('AWS::Cognito::UserPoolClient', 1);
    template.resourceCountIs('AWS::Cognito::IdentityPool', 1);
    template.resourceCountIs('AWS::Cognito::UserPoolIdentityProvider', 0);
    template.resourceCountIs('AWS::Cognito::UserPoolDomain', 0);
    template.resourceCountIs('AWS::Lambda::Function', 0);
  });

  it('creates secret-backed Google and LINE providers with a code-only public client', () => {
    const template = createTemplate(true);

    template.resourceCountIs('AWS::Cognito::UserPoolClient', 2);
    template.resourceCountIs('AWS::Cognito::IdentityPool', 1);
    template.resourceCountIs('AWS::Cognito::UserPoolIdentityProvider', 2);
    template.resourceCountIs('AWS::Lambda::Function', 1);
    template.hasResourceProperties('AWS::Cognito::UserPoolIdentityProvider', {
      ProviderName: 'Google',
      ProviderType: 'Google',
      ProviderDetails: Match.objectLike({
        authorize_scopes: 'openid email profile',
        client_id: GOOGLE_CLIENT_ID,
      }),
      AttributeMapping: Match.objectLike({
        email: 'email',
        email_verified: 'email_verified',
        name: 'name',
      }),
    });
    template.hasResourceProperties('AWS::Cognito::UserPoolIdentityProvider', {
      ProviderName: 'LINE',
      ProviderType: 'OIDC',
      ProviderDetails: Match.objectLike({
        authorize_scopes: 'openid profile email',
        client_id: LINE_CHANNEL_ID,
        oidc_issuer: 'https://access.line.me',
      }),
      AttributeMapping: Match.objectLike({
        email: 'email',
        name: 'name',
        picture: 'picture',
      }),
    });
    template.hasResourceProperties('AWS::Cognito::UserPool', {
      LambdaConfig: Match.objectLike({ PreSignUp: Match.anyValue() }),
    });
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: 'cognito-idp:AdminLinkProviderForUser',
            Effect: 'Allow',
          }),
        ]),
        Version: '2012-10-17',
      },
      Roles: ['kinsun-staging-web-bff'],
    });
    template.hasResourceProperties('AWS::Cognito::UserPoolDomain', {
      Domain: 'kinsun-staging-auth-test',
    });
    template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
      ClientName: 'elderly-care-web-bff-staging',
      GenerateSecret: false,
      AllowedOAuthFlows: ['code'],
      AllowedOAuthFlowsUserPoolClient: true,
      AllowedOAuthScopes: ['openid', 'email', 'profile'],
      CallbackURLs: [CALLBACK_URL],
      LogoutURLs: [LOGOUT_URL],
      SupportedIdentityProviders: ['Google', 'LINE'],
      EnableTokenRevocation: true,
      PreventUserExistenceErrors: 'ENABLED',
      RefreshTokenRotation: {
        Feature: 'ENABLED',
        RetryGracePeriodSeconds: 10,
      },
    });

    const providers = template.findResources('AWS::Cognito::UserPoolIdentityProvider');
    for (const providerName of ['Google', 'LINE']) {
      const provider = Object.values(providers).find(
        (resource) => resource.Properties.ProviderName === providerName,
      );
      assert.ok(provider);
      const providerSecret = provider.Properties.ProviderDetails.client_secret;
      assert.equal(typeof providerSecret, 'string');
      assert.match(providerSecret, /^\{\{resolve:secretsmanager:/);
    }

    const synthesized = JSON.stringify(template.toJSON());
    assert.match(synthesized, /resolve:secretsmanager/);
    assert.equal(template.toJSON().Outputs, undefined);

    const clients = template.findResources('AWS::Cognito::UserPoolClient');
    const legacyClientLogicalId = Object.entries(clients).find(
      ([, resource]) => resource.Properties.ClientName === undefined,
    )?.[0];
    const identityPools = template.findResources('AWS::Cognito::IdentityPool');
    const identityPool = Object.values(identityPools)[0];
    assert.ok(legacyClientLogicalId);
    assert.ok(identityPool);
    assert.deepEqual(identityPool.Properties.CognitoIdentityProviders[0].ClientId, {
      Ref: legacyClientLogicalId,
    });
  });

  it('orders the web client after both providers and the managed-login domain', () => {
    const template = createTemplate(true);
    const providers = template.findResources('AWS::Cognito::UserPoolIdentityProvider');
    const domains = template.findResources('AWS::Cognito::UserPoolDomain');
    const clients = template.findResources('AWS::Cognito::UserPoolClient');
    const providerLogicalIds = Object.keys(providers);
    const domainLogicalId = Object.keys(domains)[0];
    const webClient = Object.values(clients).find(
      (resource) => resource.Properties.ClientName === 'elderly-care-web-bff-staging',
    );

    assert.equal(providerLogicalIds.length, 2);
    assert.ok(domainLogicalId);
    assert.ok(webClient);
    const dependencies = Array.isArray(webClient.DependsOn)
      ? webClient.DependsOn
      : [webClient.DependsOn];
    for (const providerLogicalId of providerLogicalIds) {
      assert.ok(dependencies.includes(providerLogicalId));
    }
    assert.ok(dependencies.includes(domainLogicalId));
  });
});

describe('ElderlyCareStack login federation integration', () => {
  it('passes staging settings and outputs only public integration values', () => {
    const app = new cdk.App();
    const stack = new ElderlyCareStack(app, 'StagingIntegrationTestStack', {
      envName: 'staging',
      env: { account: '111111111111', region: 'us-west-2' },
      googleFederation: {
        clientId: GOOGLE_CLIENT_ID,
        clientSecret: cdk.SecretValue.secretsManager(GOOGLE_SECRET_NAME),
        domainPrefix: 'kinsun-staging-integration-test',
        callbackUrls: [CALLBACK_URL],
        logoutUrls: [LOGOUT_URL],
      },
      lineLoginFederation: {
        channelId: LINE_CHANNEL_ID,
        channelSecret: cdk.SecretValue.secretsManager(LINE_SECRET_NAME),
        bffExecutionRoleArn: LINE_BFF_ROLE_ARN,
      },
    });
    const template = Template.fromStack(stack);

    template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
      ClientName: 'elderly-care-web-bff-staging',
      CallbackURLs: [CALLBACK_URL],
      LogoutURLs: [LOGOUT_URL],
      SupportedIdentityProviders: ['Google', 'LINE'],
    });
    template.hasOutput('WebBffClientId', {});
    template.hasOutput('CognitoOAuthDomain', {});
    template.hasOutput('GoogleOAuthRedirectUri', {});
    template.hasOutput('LineLoginCognitoRedirectUri', {});
    template.hasOutput('LineLoginProviderName', { Value: 'LINE' });
    template.hasOutput('LineLoginChannelId', { Value: LINE_CHANNEL_ID });

    const serializedOutputs = JSON.stringify(template.toJSON().Outputs);
    assert.match(serializedOutputs, /oauth2\/idpresponse/);
    assert.doesNotMatch(
      serializedOutputs,
      /client_secret|secretsmanager|kinsun\/staging\/(?:google-oauth|line-login)/i,
    );
  });

  it('rejects parent-stack federation outside staging', () => {
    const app = new cdk.App();

    assert.throws(
      () =>
        new ElderlyCareStack(app, 'ProductionIntegrationTestStack', {
          envName: 'production',
          googleFederation: {
            clientId: GOOGLE_CLIENT_ID,
            clientSecret: cdk.SecretValue.secretsManager(GOOGLE_SECRET_NAME),
            domainPrefix: 'must-not-be-created',
            callbackUrls: [CALLBACK_URL],
            logoutUrls: [LOGOUT_URL],
          },
        }),
      /only for the staging stack/,
    );
  });
});
