# fooroh

Bot for Bluesky that adds watermarks to posted illustrations and replaces them with reposts.
The name `fooroh` comes from the Japanese word `封蝋`, which means sealing wax.

# System Design

![](./docs/system-design.drawio.svg)

## Requirements

Serverless Bluesky bot deployable on AWS via AWS CDK.
The application part is a Lambda function or ECS service written in python and deployed as a Docker container image.

**deploy target**

* AWS Account

**local development environment**

* AWS CLI
* Node.js
* Python 3.13.x
* Poetry 2.x
* Docker Service
* node

## quick start

```bash
$ npm install
$ npx cdk bootstrap --profile default
$ npx cdk synth --profile default -c env=dev --all
$ npx cdk deploy --profile default -c env=dev --all

# deploy each Stack
$ npx cdk deploy fooroh-CommonResourceStack-dev -c env=dev
$ npx cdk deploy fooroh-FollowFlowStack-dev -c env=dev
$ npx cdk deploy fooroh-SignupFlowStack-dev -c env=dev
$ npx cdk deploy fooroh-SetWatermarkImgStack-dev -c env=dev
$ npx cdk deploy fooroh-WatermarkingFlowStack-dev -c env=dev
$ npx cdk deploy fooroh-SignoutFlowStack-dev -c env=dev
$ npx cdk deploy fooroh-FirehoseStack-dev -c env=dev
```

## Design

[Systen Design](docs/system-design.drawio)

