import * as cdk from 'aws-cdk-lib';
import { Duration } from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import { CommonResourceStack } from './common-resource-stack';

export class WatermarkingFlowStack extends cdk.Stack {
  private readonly getImageLambda: lambda.DockerImageFunction;
  private readonly watermarkingLambda: lambda.DockerImageFunction;
  private readonly postWatermarkedLambda: lambda.DockerImageFunction;
  private readonly delOriginalPostLambda: lambda.DockerImageFunction;
  private readonly flow: sfn.StateMachine;

  constructor(scope: Construct, id: string, commonResource: CommonResourceStack, props?: cdk.StackProps) {
    super(scope, id, props);

    this.getImageLambda = this.createGetImageLambda(commonResource);
    this.watermarkingLambda = this.createWatermarkingLambda(commonResource);
    this.postWatermarkedLambda = this.createPostWatermarkedLambda(commonResource);
    this.delOriginalPostLambda = this.createDelOriginalPostLambda(commonResource);

    // Secrets Managerの利用権限付与
    commonResource.secretManager.grantRead(this.getImageLambda);
    commonResource.secretManager.grantRead(this.watermarkingLambda);
    commonResource.secretManager.grantRead(this.postWatermarkedLambda);
    commonResource.secretManager.grantRead(this.delOriginalPostLambda);

    // S3バケットの利用権限付与
    commonResource.originalImageBucket.grantReadWrite(this.getImageLambda);
    commonResource.originalImageBucket.grantRead(this.watermarkingLambda);
    commonResource.watermarksBucket.grantRead(this.watermarkingLambda);
    commonResource.watermarkedImageBucket.grantWrite(this.watermarkingLambda);
    commonResource.watermarkedImageBucket.grantRead(this.postWatermarkedLambda);

    // Step Functionの作成
    this.flow = this.createWorkflow(
      this.getImageLambda,
      this.watermarkingLambda,
      this.postWatermarkedLambda,
      this.delOriginalPostLambda
    );
  }

  private createWorkflow(
    getImgLambda: lambda.IFunction,
    watermarkingLambda: lambda.IFunction,
    postWatermarkedLambda: lambda.IFunction,
    delOriginalPostLambda: lambda.IFunction
  ): sfn.StateMachine {
    // Lambdaタスク定義
    const getImageTask = new tasks.LambdaInvoke(this, 'GetImage', {
      lambdaFunction: getImgLambda,
      inputPath: '$.Payload',
      outputPath: '$',
    });
    const watermarkingTask = new tasks.LambdaInvoke(this, 'Watermarking', {
      lambdaFunction: watermarkingLambda,
      inputPath: '$.Payload',
      outputPath: '$',
    });
    const postWatermarkedTask = new tasks.LambdaInvoke(this, 'PostWatermarked', {
      lambdaFunction: postWatermarkedLambda,
      inputPath: '$.Payload',
      outputPath: '$',
    });
    const delOriginalPostTask = new tasks.LambdaInvoke(this, 'DelOrgPost', {
      lambdaFunction: delOriginalPostLambda,
      inputPath: '$.Payload',
      outputPath: '$',
    });

    const definition = getImageTask.next(watermarkingTask).next(postWatermarkedTask).next(delOriginalPostTask);

    // ステートマシンの定義
    return new sfn.StateMachine(this, 'WatermarkingFlow', {
      definition,
      timeout: Duration.minutes(10),
    });
  }



  private createGetImageLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-watermarking-get_image`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['watermarking.get_image.handler'],
    });
    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
        ORIGINAL_IMAGE_BUCKET: commonResource.originalImageBucket.bucketName,
      },
    });
  }

  private createWatermarkingLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-watermarking-watermarking`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['watermarking.watermarking.handler'],
    });
    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
        ORIGINAL_IMAGE_BUCKET: commonResource.originalImageBucket.bucketName,
        WATERMARKS_IMAGE_BUCKET: commonResource.watermarksBucket.bucketName,
        WATERMARKED_IMAGE_BUCKET: commonResource.watermarkedImageBucket.bucketName,
      },
    });
  }

  private createPostWatermarkedLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-watermarking-post-watermarked`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['watermarking.post_watermarked.handler'],
    });
    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
        WATERMARKED_IMAGE_BUCKET: commonResource.watermarkedImageBucket.bucketName,
      },
    });
  }

  private createDelOriginalPostLambda(commonResource: CommonResourceStack): lambda.DockerImageFunction {
    const name = `${this.stackName}-watermarking-del-original-post`;
    const code = lambda.DockerImageCode.fromImageAsset('.', {
      cmd: ['watermarking.del_original_post.handler'],
    });
    return new lambda.DockerImageFunction(this, name.toLowerCase(), {
      functionName: name,
      code,
      environment: {
        LOG_LEVEL: commonResource.loglevel,
        SECRET_NAME: commonResource.secretManager.secretName,
      },
    });
  }
}
