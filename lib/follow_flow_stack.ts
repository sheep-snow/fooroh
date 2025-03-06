import { Duration, Stack, StackProps } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as pipes from 'aws-cdk-lib/aws-pipes';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import { CommonResourceStack } from './common-resource-stack';

export class FollowFlowStack extends Stack {
  private readonly touchUserFileLambda: lambda.DockerImageFunction;
  private readonly followbackLambda: lambda.DockerImageFunction;
  private readonly sendDmLambda: lambda.DockerImageFunction;
  private readonly flow: sfn.StateMachine;

  constructor(scope: Construct, id: string, commonResource: CommonResourceStack, props?: StackProps) {
    super(scope, id, props);

    this.touchUserFileLambda = this.createTouchUserFileLambda(commonResource);
    this.followbackLambda = this.createFollowbackLambda(commonResource);
    this.sendDmLambda = this.createSendDmLambda(commonResource);

    commonResource.secretManager.grantRead(this.touchUserFileLambda);
    commonResource.secretManager.grantRead(this.followbackLambda);
    commonResource.secretManager.grantRead(this.sendDmLambda);

    commonResource.userinfoBucket.grantReadWrite(this.touchUserFileLambda);
    commonResource.userinfoBucket.grantReadWrite(this.followbackLambda);
    commonResource.userinfoBucket.grantReadWrite(this.sendDmLambda);

    this.flow = this.createWorkflow(this.touchUserFileLambda, this.followbackLambda, this.sendDmLambda);

    this.createEventbridgePipe(commonResource);
  }

  private createEventbridgePipe(commonResource: CommonResourceStack): void {
    const pipesRole = new iam.Role(this, 'FollowFlowPipesRole', {
      assumedBy: new iam.ServicePrincipal('pipes.amazonaws.com'),
    });

    commonResource.followedQueue.grantConsumeMessages(pipesRole);
    this.flow.grantStartExecution(pipesRole);

    const pipeName = `${this.stackName}-follow-flow-pipe`;
    new pipes.CfnPipe(this, pipeName, {
      name: pipeName,
      roleArn: pipesRole.roleArn,
      source: commonResource.followedQueue.queueArn,
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

  private createWorkflow(touchUserFileLambda: lambda.DockerImageFunction, followbackLambda: lambda.DockerImageFunction, sendDmLambda: lambda.DockerImageFunction): sfn.StateMachine {
    const touchUserFileTask = new tasks.LambdaInvoke(this, 'TouchUserFile', {
      lambdaFunction: touchUserFileLambda,
      inputPath: '$.[0].body',
      outputPath: '$',
    });

    const followbackTask = new tasks.LambdaInvoke(this, 'Followback', {
      lambdaFunction: followbackLambda,
      inputPath: '$.Payload',
      outputPath: '$',
    });

    const sendDmTask = new tasks.LambdaInvoke(this, 'SendDM', {
      lambdaFunction: sendDmLambda,
      inputPath: '$.Payload',
      outputPath: '$',
    });

    const definition = touchUserFileTask.next(followbackTask).next(sendDmTask);

    return new sfn.StateMachine(this, 'FollowFlow', {
      definition,
      timeout: Duration.minutes(5),
    });
  }

  private createTouchUserFileLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-follow-touch_user_file`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['follow.touch_user_file.handler'],
    });

    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
        USERINFO_BUCKET_NAME: commonResource.userinfoBucket.bucketName,
      },
      timeout: Duration.seconds(60),
      memorySize: 256,
      retryAttempts: 0,
    });
  }

  private createFollowbackLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-follow-followback`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['follow.followback.handler'],
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

  private createSendDmLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-follow-send_dm`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['follow.send_dm.handler'],
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
}
