#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { Environment } from 'aws-cdk-lib';
import 'source-map-support/register';
import { CommonResourceStack } from '../lib/common-resource-stack';
import { FirehoseStack } from '../lib/firehose_stack';
import { FollowFlowStack } from '../lib/follow_flow_stack';
import { SetWatermarkImgStack } from '../lib/set_watermark_img_stack';
import { SignoutFlowStack } from '../lib/signout_flow_stack';
import { SignupFlowStack } from '../lib/signup_flow_stack';
import { WatermarkingFlowStack } from '../lib/watermarking_flow_stack';

const app = new cdk.App();

const VALID_STAGES = ["dev", "prod"];
const stage = app.node.tryGetContext("env");
if (!VALID_STAGES.includes(stage)) {
  throw new Error("Please specify the context. i.e. `--context env=dev|prod`");
}
const ctx = app.node.tryGetContext(stage);
const env: Environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

const appName = ctx["app_name"];
const common = new CommonResourceStack(app, `${appName}-CommonResourceStack-${stage}`, {
  contextJson: ctx,
  env: env,
  stage: stage,
  appName: ctx["app_name"],
  imageExpirationDays: parseInt(ctx["image_expiration_days"]),
  userinfoExpirationDays: parseInt(ctx["userinfo_expiration_days"]),
  logLevel: ctx["loglevel"],
  vpcCidr: ctx["vpc-cidr"],
  vpcMask: parseInt(ctx["vpc-mask"]),
  maxRetries: parseInt(ctx["max_retries"]),
  maxCapacity: parseInt(ctx["max_capacity"]),
});
const follow = new FollowFlowStack(app, `${appName}-FollowFlowStack-${stage}`, common, { env });
const signup = new SignupFlowStack(app, `${appName}-SignupFlowStack-${stage}`, common, { env });
const setWatermarkImg = new SetWatermarkImgStack(app, `${appName}-SetWatermarkImgStack-${stage}`, common, { env });
const watermarking = new WatermarkingFlowStack(app, `${appName}-WatermarkingFlowStack-${stage}`, common, { env });
const signout = new SignoutFlowStack(app, `${appName}-SignoutFlowStack-${stage}`, common, { env });
const firehose = new FirehoseStack(app, `${appName}-FirehoseStack-${stage}`, common, { env });

app.synth();