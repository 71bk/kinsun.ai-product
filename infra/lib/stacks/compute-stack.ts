import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecsPatterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as events from 'aws-cdk-lib/aws-events';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import { Construct } from 'constructs';

export interface ComputeStackProps extends cdk.StackProps {
  vpc: ec2.IVpc;
  database: rds.IDatabaseCluster;
  eventBus: events.IEventBus;
  kmsKey: kms.IKey;
}

export class ComputeStack extends cdk.Stack {
  public readonly cluster: ecs.ICluster;

  constructor(scope: Construct, id: string, props: ComputeStackProps) {
    super(scope, id, props);

    // ECS Cluster
    this.cluster = new ecs.Cluster(this, 'Cluster', {
      vpc: props.vpc,
      containerInsights: true,
    });

    // ECR Repository for Core API
    const repo = new ecr.Repository(this, 'CoreApiRepo', {
      repositoryName: `${this.stackName}-core-api`,
      imageScanOnPush: true,
      lifecycleRules: [{ maxImageCount: 10 }],
    });

    // Fargate Service (Core API - Python FastAPI)
    // NOTE: Image will be pushed by CI/CD pipeline
    // This is the skeleton - actual service definition added after first image push
    
    new cdk.CfnOutput(this, 'ClusterName', { value: this.cluster.clusterName });
    new cdk.CfnOutput(this, 'RepoUri', { value: repo.repositoryUri });
  }
}
