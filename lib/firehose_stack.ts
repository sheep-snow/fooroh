import { Stack, StackProps } from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { DockerImageAsset } from 'aws-cdk-lib/aws-ecr-assets';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { CommonResourceStack } from './common-resource-stack';

export class FirehoseStack extends Stack {
  private readonly imageAsset: DockerImageAsset;

  constructor(scope: Construct, id: string, commonResource: CommonResourceStack, props?: StackProps) {
    super(scope, id, props);

    this.imageAsset = this.buildAndPushImage();
    this.createEcsService(commonResource);
  }

  private createEcsService(commonResource: CommonResourceStack): void {
    const vpcName = `${commonResource.appName}-${commonResource.stage}-vpc`;
    const vpc = new ec2.Vpc(this, vpcName, {
      vpcName: vpcName,
      ipAddresses: ec2.IpAddresses.cidr(commonResource.vpcCidr),
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: commonResource.vpcMask,
        },
      ],
    });

    const sgName = `${commonResource.appName}-${commonResource.stage}-ecs-sg`;
    const sg = new ec2.SecurityGroup(this, sgName, {
      vpc: vpc,
      securityGroupName: sgName,
      allowAllOutbound: true,
    });

    const clusterName = `${commonResource.appName}-${commonResource.stage}-cluster`;
    const cluster = new ecs.Cluster(this, clusterName, {
      clusterName: clusterName,
      vpc: vpc,
      enableFargateCapacityProviders: true,
    });

    const taskName = `${commonResource.appName}-${commonResource.stage}-task`;
    const taskDefinition = new ecs.FargateTaskDefinition(this, taskName, {
      cpu: 256,
      memoryLimitMiB: 2048,
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.X86_64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });

    commonResource.secretManager.grantRead(taskDefinition.taskRole);
    const logGroup = new logs.LogGroup(this, `${commonResource.appName}-${commonResource.stage}-ecs-log-group`, {
      logGroupName: `/ecs/${commonResource.appName}/${commonResource.stage}`,
      retention: logs.RetentionDays.THREE_DAYS,
    });

    const logDriver = new ecs.AwsLogDriver({
      logGroup: logGroup,
      streamPrefix: 'firehose',
    });

    const serviceName = `${commonResource.appName}-${commonResource.stage}-service`;
    taskDefinition.addContainer('firehose', {
      image: ecs.ContainerImage.fromDockerImageAsset(this.imageAsset),
      logging: logDriver,
      environment: {
        FOLLOWED_QUEUE_URL: commonResource.followedQueue.queueUrl,
        SET_WATERMARK_IMG_QUEUE_URL: commonResource.setWatermarkImgQueue.queueUrl,
        WATERMARKING_QUEUE_URL: commonResource.watermarkingQueue.queueUrl,
        SECRET_NAME: commonResource.secretManager.secretName,
        CLUSTER_NAME: cluster.clusterName,
        SERVICE_NAME: serviceName,
      },
    });

    commonResource.followedQueue.grantSendMessages(taskDefinition.taskRole);
    commonResource.setWatermarkImgQueue.grantSendMessages(taskDefinition.taskRole);
    commonResource.watermarkingQueue.grantSendMessages(taskDefinition.taskRole);

    const service = new ecs.FargateService(this, serviceName, {
      serviceName: serviceName,
      cluster: cluster,
      taskDefinition: taskDefinition,
      minHealthyPercent: 100,
      capacityProviderStrategies: [
        {
          capacityProvider: 'FARGATE_SPOT',
          weight: 1,
        },
      ],
      securityGroups: [sg],
      desiredCount: 0,  // Set desiredCount to 0 to prevent the service from starting automatically
      assignPublicIp: true,
      enableExecuteCommand: true,
    });

    taskDefinition.taskRole.addToPrincipalPolicy(new iam.PolicyStatement({
      actions: ['ecs:DescribeTasks', 'ecs:StopTask'],
      resources: ['*'],
    }));
  }

  private buildAndPushImage(): DockerImageAsset {
    const imgName = 'firehose';
    return new DockerImageAsset(this, imgName, {
      directory: '.',
      file: 'ecs.Dockerfile',
    });
  }
}
