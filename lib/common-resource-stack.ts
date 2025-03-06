import * as cdk from 'aws-cdk-lib';
import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';
import * as crypto from 'crypto';

interface CommonResourceStackProps extends cdk.StackProps {
  contextJson: any;
  stage: string;
  appName: string;
  imageExpirationDays: number;
  userinfoExpirationDays: number;
  logLevel: string;
  vpcCidr: string;
  vpcMask: number;
  maxRetries: number;
  maxCapacity: number;
}

export class CommonResourceStack extends cdk.Stack {
  public readonly secretManager: secretsmanager.ISecret;
  public readonly userinfoBucket: s3.IBucket;
  public readonly followedQueue: sqs.IQueue;
  public readonly loglevel: string;
  public readonly stage: string;
  public readonly envVars: any;
  public readonly awsAccount: string;
  public readonly appName: string;
  public readonly imageExpirationDays: number;
  public readonly userinfoExpirationDays: number;

  public readonly originalImageBucket: s3.IBucket;
  public readonly watermarksBucket: s3.IBucket;
  public readonly watermarkedImageBucket: s3.IBucket;
  public readonly setWatermarkImgQueue: sqs.IQueue;
  public readonly watermarkingQueue: sqs.IQueue;
  public readonly ecsExecutionRole: iam.IRole;
  public readonly ecsTaskRole: iam.IRole;

  public readonly vpcCidr: string;
  public readonly vpcMask: number;
  public readonly maxRetries: number;
  public readonly maxCapacity: number;

  constructor(scope: Construct, id: string, props: CommonResourceStackProps) {
    super(scope, id, props);

    this.stage = props.stage;
    this.envVars = props.contextJson;
    this.awsAccount = cdk.Stack.of(this).account;
    this.appName = props.appName;
    this.imageExpirationDays = props.imageExpirationDays;
    this.userinfoExpirationDays = props.userinfoExpirationDays;
    this.loglevel = props.logLevel;
    this.vpcCidr = props.vpcCidr;
    this.vpcMask = props.vpcMask;
    this.maxRetries = props.maxRetries;
    this.maxCapacity = props.maxCapacity;

    // リソースの作成
    this.secretManager = this.createSecretManager();
    this.loglevel = props.contextJson.log_level;
    this.originalImageBucket = this.createOriginalImageBucket();
    this.watermarksBucket = this.createWatermarksBucket();
    this.watermarkedImageBucket = this.createWatermarkedImageBucket();
    this.userinfoBucket = this.createUserinfoBucket();
    this.followedQueue = this.createFollowedQueue();
    this.setWatermarkImgQueue = this.createSetWatermarkImgQueue();
    this.watermarkingQueue = this.createWatermarkingQueue();
    this.ecsExecutionRole = this.createEcsExecutionRole();
    this.ecsTaskRole = this.createEcsTaskRole();
  }

  private checkSecretExists(secretId: string): boolean {
    // すでにシークレットが存在するか確認
    try {
      secretsmanager.Secret.fromSecretNameV2(this, secretId, secretId);
      return true;
    }
    catch (e) {
      return false;
    }
  }

  private createSecretManager(): secretsmanager.ISecret {
    const secretId = `${this.appName}-secretsmanager-${this.stage}`.toLowerCase();
    if (this.checkSecretExists(secretId)) {
      // 既存のシークレットを参照
      const existingSecret = secretsmanager.Secret.fromSecretNameV2(this, 'ExistingSecret', secretId);
      new cdk.CfnOutput(this, 'ExistingSecretOutput', { value: `Using existing secret: ${secretId}` });
      return existingSecret;
    } else {
      const defaultSecret = JSON.stringify({
        fernet_key: crypto.randomBytes(32).toString('base64'),
        bot_userid: '?????.bsky.social',
        bot_app_password: 'somepassword',
        ignore_list_uri: 'https://bsky.app/profile/did:plc:xxxx/lists/xxxxx',
        white_list_uri: 'https://bsky.app/profile/did:plc:xxxx/lists/xxxxx',
      });
      new cdk.CfnOutput(this, 'SecretCreated', { value: `Created new secret: ${secretId}` });
      return new secretsmanager.Secret(this, secretId, {
        secretName: secretId,
        description: 'A secret for storing credentials',
        removalPolicy: RemovalPolicy.RETAIN,
        generateSecretString: {
          secretStringTemplate: defaultSecret,
          generateStringKey: 'password',
        },
      });
    }
  }

  private createOriginalImageBucket(): s3.IBucket {
    const originalBucketId = `${this.appName}-original-imgs-${this.stage}-${this.awsAccount}`.toLowerCase();
    return new s3.Bucket(this, originalBucketId, {
      bucketName: originalBucketId,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [{ expiration: Duration.days(this.imageExpirationDays) }],
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
    });
  }

  private createWatermarksBucket(): s3.IBucket {
    const watermarksBucketId = `${this.appName}-watermarks-${this.stage}-${this.awsAccount}`.toLowerCase();
    return new s3.Bucket(this, watermarksBucketId, {
      bucketName: watermarksBucketId,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });
  }

  private createWatermarkedImageBucket(): s3.IBucket {
    const watermarkedBucketId = `${this.appName}-watermarked-imgs-${this.stage}-${this.awsAccount}`.toLowerCase();
    return new s3.Bucket(this, watermarkedBucketId, {
      bucketName: watermarkedBucketId,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [{ expiration: Duration.days(this.imageExpirationDays) }],
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
    });
  }

  private createUserinfoBucket(): s3.IBucket {
    const userinfoBucketId = `${this.appName}-userinfo-files-${this.stage}-${this.awsAccount}`.toLowerCase();
    return new s3.Bucket(this, userinfoBucketId, {
      bucketName: userinfoBucketId,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
    });
  }

  private createFollowedQueue(): sqs.IQueue {
    return new sqs.Queue(this, `${this.appName}-followed-queue-${this.stage}`, {
      queueName: `${this.appName}-followed-queue-${this.stage}`,
      visibilityTimeout: Duration.seconds(30),
      retentionPeriod: Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });
  }

  private createSetWatermarkImgQueue(): sqs.IQueue {
    return new sqs.Queue(this, `${this.appName}-set-watermark-img-queue-${this.stage}`, {
      queueName: `${this.appName}-set-watermark-img-queue-${this.stage}`,
      visibilityTimeout: Duration.seconds(30),
      retentionPeriod: Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });
  }

  private createWatermarkingQueue(): sqs.IQueue {
    return new sqs.Queue(this, `${this.appName}-watermarking-queue-${this.stage}`, {
      queueName: `${this.appName}-watermarking-queue-${this.stage}`,
      visibilityTimeout: Duration.seconds(30),
      retentionPeriod: Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });
  }

  private createEcsExecutionRole(): iam.IRole {
    return new iam.Role(this, `${this.appName}-ecs_execution_role-${this.stage}`, {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
      ],
    });
  }

  private createEcsTaskRole(): iam.IRole {
    return new iam.Role(this, `${this.appName}-ecs_task_role-${this.stage}`, {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSQSFullAccess'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonS3FullAccess'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSNSFullAccess'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonDynamoDBFullAccess'),
      ],
    });
  }
}
