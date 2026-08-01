import * as cdk from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

export class EventStack extends cdk.Stack {
  public readonly eventBus: events.IEventBus;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // EventBridge custom bus
    this.eventBus = new events.EventBus(this, 'EventBus', {
      eventBusName: `${this.stackName}-bus`,
    });

    // Dead Letter Queue
    const dlq = new sqs.Queue(this, 'DLQ', {
      queueName: `${this.stackName}-dlq`,
      retentionPeriod: cdk.Duration.days(14),
    });

    // Care Event Processing Queue
    const careEventQueue = new sqs.Queue(this, 'CareEventQueue', {
      queueName: `${this.stackName}-care-events`,
      visibilityTimeout: cdk.Duration.seconds(60),
      deadLetterQueue: { queue: dlq, maxReceiveCount: 3 },
    });

    // Summary Generation Queue
    const summaryQueue = new sqs.Queue(this, 'SummaryQueue', {
      queueName: `${this.stackName}-summary`,
      visibilityTimeout: cdk.Duration.seconds(120),
      deadLetterQueue: { queue: dlq, maxReceiveCount: 3 },
    });

    // Notification Delivery Queue
    const notificationQueue = new sqs.Queue(this, 'NotificationQueue', {
      queueName: `${this.stackName}-notification`,
      visibilityTimeout: cdk.Duration.seconds(30),
      deadLetterQueue: { queue: dlq, maxReceiveCount: 5 },
    });

    new cdk.CfnOutput(this, 'EventBusName', { value: this.eventBus.eventBusName });
    new cdk.CfnOutput(this, 'DLQUrl', { value: dlq.queueUrl });
  }
}
