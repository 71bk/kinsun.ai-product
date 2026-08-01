#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { NetworkStack } from '../lib/stacks/network-stack';
import { SecurityStack } from '../lib/stacks/security-stack';
import { DatabaseStack } from '../lib/stacks/database-stack';
import { StorageStack } from '../lib/stacks/storage-stack';
import { ComputeStack } from '../lib/stacks/compute-stack';
import { EventStack } from '../lib/stacks/event-stack';
import { MonitoringStack } from '../lib/stacks/monitoring-stack';

const app = new cdk.App();

const env = app.node.tryGetContext('env') || 'dev';
const projectName = app.node.tryGetContext('projectName') || 'elderly-care';

const envConfig: Record<string, cdk.Environment> = {
  dev: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'ap-northeast-1' },
  staging: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'ap-northeast-1' },
  prod: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'ap-northeast-1' },
};

const stackProps: cdk.StackProps = {
  env: envConfig[env],
  tags: {
    Project: projectName,
    Environment: env,
    ManagedBy: 'cdk',
  },
};

const network = new NetworkStack(app, `${projectName}-${env}-network`, stackProps);
const security = new SecurityStack(app, `${projectName}-${env}-security`, {
  ...stackProps,
  vpc: network.vpc,
});
const database = new DatabaseStack(app, `${projectName}-${env}-database`, {
  ...stackProps,
  vpc: network.vpc,
  kmsKey: security.dataKey,
});
const storage = new StorageStack(app, `${projectName}-${env}-storage`, {
  ...stackProps,
  kmsKey: security.dataKey,
});
const events = new EventStack(app, `${projectName}-${env}-events`, stackProps);
const compute = new ComputeStack(app, `${projectName}-${env}-compute`, {
  ...stackProps,
  vpc: network.vpc,
  database: database.cluster,
  eventBus: events.eventBus,
  kmsKey: security.dataKey,
});
new MonitoringStack(app, `${projectName}-${env}-monitoring`, stackProps);

app.synth();
