import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

export interface StorageStackProps extends cdk.StackProps {
  kmsKey: kms.IKey;
}

export class StorageStack extends cdk.Stack {
  public readonly audioBucket: s3.IBucket;
  public readonly knowledgeBucket: s3.IBucket;

  constructor(scope: Construct, id: string, props: StorageStackProps) {
    super(scope, id, props);

    // Audio storage (voice recordings, transcripts)
    this.audioBucket = new s3.Bucket(this, 'AudioBucket', {
      bucketName: `${this.stackName}-audio`,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: props.kmsKey,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: false,
      lifecycleRules: [
        { expiration: cdk.Duration.days(90), id: 'expire-audio-90d' },
      ],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Knowledge base documents (RAG source, chunks, embeddings)
    this.knowledgeBucket = new s3.Bucket(this, 'KnowledgeBucket', {
      bucketName: `${this.stackName}-knowledge`,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: props.kmsKey,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    new cdk.CfnOutput(this, 'AudioBucketName', { value: this.audioBucket.bucketName });
    new cdk.CfnOutput(this, 'KnowledgeBucketName', { value: this.knowledgeBucket.bucketName });
  }
}
