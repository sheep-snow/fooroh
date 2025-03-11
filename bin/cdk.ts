#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { Environment } from 'aws-cdk-lib';
import * as dotenv from "dotenv";
import 'source-map-support/register';
import { CommonResourceStack } from '../lib/common-resource-stack';
import { FirehoseStack } from '../lib/firehose_stack';
import { FollowFlowStack } from '../lib/follow_flow_stack';
import { SetWatermarkImgStack } from '../lib/set_watermark_img_stack';
import { SignoutFlowStack } from '../lib/signout_flow_stack';
import { SignupFlowStack } from '../lib/signup_flow_stack';
import { WatermarkingFlowStack } from '../lib/watermarking_flow_stack';

dotenv.config({ path: './cdk.env' });
if (process.env.APP_NAME == undefined || process.env.APP_NAME.length == 0) {
  throw new Error("Please set valiables to cdk.env file");
}
const app = new cdk.App();
const VALID_STAGES = ["dev", "prod"];
const stage = app.node.tryGetContext("env");
if (!VALID_STAGES.includes(stage)) {
  throw new Error("Please specify the context. i.e. `--context env=dev|prod`");
}
const env: Environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

const appName = process.env.APP_NAME || "fooroh";
const common = new CommonResourceStack(app, `${appName}-CommonResourceStack-${stage}`, {
  contextJson: process.env,
  env: env,
  stage: stage,
  appName: appName,
  imageExpirationDays: parseInt(process.env.IMAGE_EXPIRATION_DAYS || '0'),
  userinfoExpirationDays: parseInt(process.env.USERINFO_EXPIRATION_DAYS || '0'),
  logLevel: process.env.LOGLEVEL || "DEBUG",
  vpcCidr: process.env.VPC_CIDR || "10.35.0.0/24",
  vpcMask: parseInt(process.env.VPC_MASK || '26'),
  maxRetries: parseInt(process.env.MAX_RETRIES || '0'),
  maxCapacity: parseInt(process.env.MAX_CAPACITY || '0'),
});

const follow = new FollowFlowStack(app, `${appName}-FollowFlowStack-${stage}`, common, { env });
const signup = new SignupFlowStack(app, `${appName}-SignupFlowStack-${stage}`, common, { env });
const setWatermarkImg = new SetWatermarkImgStack(app, `${appName}-SetWatermarkImgStack-${stage}`, common, { env });
const watermarking = new WatermarkingFlowStack(app, `${appName}-WatermarkingFlowStack-${stage}`, common, { env });
const signout = new SignoutFlowStack(app, `${appName}-SignoutFlowStack-${stage}`, common, { env });
const firehose = new FirehoseStack(app, `${appName}-FirehoseStack-${stage}`, common, { env });
// Tagging all resources
cdk.Tags.of(app).add("category", appName);
app.synth();
