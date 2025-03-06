import { Duration, Stack, StackProps } from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdaEventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import { CommonResourceStack } from './common-resource-stack';

export class SetWatermarkImgStack extends Stack {
  private readonly executorLambda: lambda.DockerImageFunction;
  private readonly notifierLambda: lambda.DockerImageFunction;
  private readonly flow: sfn.StateMachine;

  constructor(scope: Construct, id: string, commonResource: CommonResourceStack, props?: StackProps) {
    super(scope, id, props);

    this.executorLambda = this.createExecutorLambda(commonResource);
    this.executorLambda.addEventSource(new lambdaEventSources.SqsEventSource(commonResource.setWatermarkImgQueue));
    this.notifierLambda = this.createNotifierLambda(commonResource);

    commonResource.secretManager.grantRead(this.executorLambda);
    commonResource.secretManager.grantRead(this.notifierLambda);

    commonResource.watermarksBucket.grantReadWrite(this.executorLambda);
    commonResource.watermarksBucket.grantReadWrite(this.notifierLambda);

    this.flow = this.createWorkflow(this.notifierLambda);
    this.executorLambda.addEnvironment("STATEMACHINE_ARN", this.flow.stateMachineArn);
  }

  private createWorkflow(notifierLambda: lambda.DockerImageFunction): sfn.StateMachine {
    const notifierTask = new tasks.LambdaInvoke(this, 'notifier', {
      lambdaFunction: notifierLambda,
    });

    return new sfn.StateMachine(this, 'set_watermark_imgFlow', {
      definition: notifierTask,
      timeout: Duration.minutes(5),
    });
  }

  private createExecutorLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-set_watermark_img-executor`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['set_watermark_img.executor.handler'],
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

  private createNotifierLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-set_watermark_img-notifier`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['set_watermark_img.notifier.handler'],
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
}
