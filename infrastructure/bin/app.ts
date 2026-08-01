#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { ElderlyCareStack } from '../lib/elderly-care-stack';

const app = new cdk.App();
const envName = app.node.tryGetContext('envName') ?? process.env.ENV_NAME ?? 'dev';

new ElderlyCareStack(app, `ElderlyCareStack-${envName}`, {
  envName,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-1',
  },
  tags: { project: 'elderly-care-ai-companion', env: envName },
});
