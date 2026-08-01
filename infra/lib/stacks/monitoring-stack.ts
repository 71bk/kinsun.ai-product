import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import { Construct } from 'constructs';

export class MonitoringStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Dashboard
    const dashboard = new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: `${this.stackName}-overview`,
    });

    dashboard.addWidgets(
      new cloudwatch.TextWidget({
        markdown: '# 智慧長照 AI 陪伴系統\n## System Overview Dashboard',
        width: 24,
        height: 2,
      })
    );

    // TODO: Add metrics widgets after compute/database stacks are deployed
    // - API latency p50/p95
    // - ASR/LLM/TTS latency
    // - Error rates
    // - Queue depth/age
    // - Database connections
  }
}
