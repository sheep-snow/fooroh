import { Duration, Stack, StackProps } from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as pipes from 'aws-cdk-lib/aws-pipes';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import { CommonResourceStack } from './common-resource-stack';

export class SignoutFlowStack extends Stack {
  private readonly cronRule: events.Rule;
  private readonly signoutQueue: sqs.Queue;
  private readonly findFollowEventsLambda: lambda.DockerImageFunction;
  private readonly delUserFilesLambda: lambda.DockerImageFunction;
  private readonly delWatermarksLambda: lambda.DockerImageFunction;
  private readonly sendDmLambda: lambda.DockerImageFunction;
  private readonly flow: sfn.StateMachine;

  constructor(scope: Construct, id: string, commonResource: CommonResourceStack, props?: StackProps) {
    super(scope, id, props);

    this.cronRule = this.createEventbridgeCronRule();
    this.signoutQueue = this.createSignoutQueue();
    this.findFollowEventsLambda = this.createFindFollowEventsLambda(commonResource);
    this.cronRule.addTarget(new targets.LambdaFunction(this.findFollowEventsLambda));
    this.signoutQueue.grantSendMessages(this.findFollowEventsLambda);
    commonResource.followedQueue.grantSendMessages(this.findFollowEventsLambda);

    this.delUserFilesLambda = this.createDelUserFilesLambda(commonResource);
    this.delWatermarksLambda = this.createDelWatermarksLambda(commonResource);
    this.sendDmLambda = this.createSendDmLambda(commonResource);

    commonResource.secretManager.grantRead(this.findFollowEventsLambda);
    commonResource.secretManager.grantRead(this.delUserFilesLambda);
    commonResource.secretManager.grantRead(this.delWatermarksLambda);
    commonResource.secretManager.grantRead(this.sendDmLambda);

    this.flow = this.createWorkflow(this.delUserFilesLambda, this.delWatermarksLambda, this.sendDmLambda);
    this.findFollowEventsLambda.addEnvironment("STATE_MACHINE_ARN", this.flow.stateMachineArn);

    this.createEventbridgePipe(this.signoutQueue);
  }

  private createEventbridgePipe(srcSqs: sqs.IQueue): void {
    const pipesRole = new iam.Role(this, 'SignOutFlowPipesRole', {
      assumedBy: new iam.ServicePrincipal('pipes.amazonaws.com'),
    });

    srcSqs.grantConsumeMessages(pipesRole);
    this.flow.grantStartExecution(pipesRole);

    const pipeName = `${this.stackName}-signout-flow-pipe`;
    new pipes.CfnPipe(this, pipeName, {
      name: pipeName,
      roleArn: pipesRole.roleArn,
      source: srcSqs.queueArn,
      sourceParameters: {
        sqsQueueParameters: {
          batchSize: 1,
        },
      },
      target: this.flow.stateMachineArn,
      targetParameters: {
        stepFunctionStateMachineParameters: {
          invocationType: 'FIRE_AND_FORGET',
        },
      },
    });
  }

  private createSignoutQueue(): sqs.Queue {
    const name = `${this.stackName}-signout-queue`;
    return new sqs.Queue(this, name, {
      queueName: name,
      visibilityTimeout: Duration.seconds(60),
      retentionPeriod: Duration.days(14),
    });
  }

  private createWorkflow(delUserFilesLambda: lambda.DockerImageFunction, delWatermarksLambda: lambda.DockerImageFunction, sendDmLambda: lambda.DockerImageFunction): sfn.StateMachine {
    const delUserFilesTask = new tasks.LambdaInvoke(this, 'DelUserfile', {
      lambdaFunction: delUserFilesLambda,
      inputPath: '$.[0].body',
      outputPath: '$',
    });

    const delWatermarksTask = new tasks.LambdaInvoke(this, 'DelWatermarks', {
      lambdaFunction: delWatermarksLambda,
      inputPath: '$.Payload',
      outputPath: '$',
    });

    const unfollowTask = new tasks.LambdaInvoke(this, 'Unfollow', {
      lambdaFunction: sendDmLambda,
      inputPath: '$.Payload',
      outputPath: '$',
    });

    const definition = delUserFilesTask.next(delWatermarksTask).next(unfollowTask);

    return new sfn.StateMachine(this, 'SignoutFlow', {
      definition,
      timeout: Duration.minutes(5),
    });
  }

  private createEventbridgeCronRule(): events.Rule {
    return new events.Rule(this, 'FindFollowEventsRule', {
      schedule: events.Schedule.rate(Duration.minutes(2)),
    });
  }

  private createFindFollowEventsLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-signout-find_followevents`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['signout.find_followevents.handler'],
    });

    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
        SIGNOUT_QUEUE_URL: this.signoutQueue.queueUrl,
        FOLLOWED_QUEUE_URL: commonResource.followedQueue.queueUrl,
      },
      timeout: Duration.seconds(120),
      description: 'Find follow events and send to SQS',
      memorySize: 512,
      retryAttempts: 0,
    });
  }

  private createDelUserFilesLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-signout-del_userfiles`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['signout.delete_user_files.handler'],
    });

    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
        USERINFO_BUCKET_NAME: commonResource.userinfoBucket.bucketName,
      },
      timeout: Duration.seconds(30),
      memorySize: 256,
      retryAttempts: 0,
    });
  }

  private createDelWatermarksLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-signout-del_watermarks`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['signout.delete_watermarks.handler'],
    });

    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
        WATERMARKS_BUCKET_NAME: commonResource.watermarksBucket.bucketName,
      },
      timeout: Duration.seconds(30),
      memorySize: 256,
      retryAttempts: 0,
    });
  }

  private createSendDmLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-unfollow`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['signout.unfollow.handler'],
    });

    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
      },
      timeout: Duration.seconds(60),
      memorySize: 256,
      retryAttempts: 0,
    });
  }
}
