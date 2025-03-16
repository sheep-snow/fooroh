import { Duration, Stack, StackProps } from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import { CommonResourceStack } from './common-resource-stack';

export class SignupFlowStack extends Stack {
  private readonly executorLambda: lambda.DockerImageFunction;
  private readonly getterLambda: lambda.DockerImageFunction;
  private readonly notifierLambda: lambda.DockerImageFunction;
  private readonly flow: sfn.StateMachine;
  private readonly cronRule: events.Rule;

  constructor(scope: Construct, id: string, commonResource: CommonResourceStack, props?: StackProps) {
    super(scope, id, props);

    this.executorLambda = this.createExecutorLambda(commonResource);
    this.getterLambda = this.createGetterLambda(commonResource);
    this.notifierLambda = this.createNotifierLambda(commonResource);

    commonResource.secretManager.grantRead(this.executorLambda);
    commonResource.secretManager.grantRead(this.getterLambda);
    commonResource.secretManager.grantRead(this.notifierLambda);

    this.flow = this.createWorkflow(this.getterLambda, this.notifierLambda);
    this.executorLambda.addEnvironment("STATEMACHINE_ARN", this.flow.stateMachineArn);
    this.flow.grantStartExecution(this.executorLambda);

    this.cronRule = this.createEventbridgeCronRule();
    this.cronRule.addTarget(new targets.LambdaFunction(this.executorLambda));
  }

  private createEventbridgeCronRule(): events.Rule {
    return new events.Rule(this, 'SignupExecutionRule', {
      schedule: events.Schedule.rate(Duration.minutes(4)),
      enabled: false,
    });
  }

  private createWorkflow(getterLambda: lambda.DockerImageFunction, notifierLambda: lambda.DockerImageFunction): sfn.StateMachine {
    const getterTask = new tasks.LambdaInvoke(this, 'getter', {
      lambdaFunction: getterLambda,
      outputPath: '$.Payload',
    });

    const notifierTask = new tasks.LambdaInvoke(this, 'notifier', {
      lambdaFunction: notifierLambda,
      outputPath: '$.Payload',
    });

    const definition = getterTask.next(notifierTask);

    return new sfn.StateMachine(this, 'SignupFlow', {
      definition,
      timeout: Duration.minutes(5),
    });
  }

  private createExecutorLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-signup-executor`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['signup.executor.handler'],
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

  private createGetterLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-signup-getter`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['signup.getter.handler'],
    });

    const func = new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
        USERINFO_BUCKET_NAME: commonResource.userinfoBucket.bucketName,
      },
      timeout: Duration.seconds(60),
      memorySize: 512,
      retryAttempts: 0,
    });

    commonResource.userinfoBucket.grantPut(func);
    return func;
  }

  private createNotifierLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-signup-notifier`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['signup.notifier.handler'],
    });

    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
      },
      timeout: Duration.seconds(30),
      memorySize: 256,
      retryAttempts: 0,
    });
  }
}
