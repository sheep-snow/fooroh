# fooroh

Bot for Bluesky that adds watermarks to posted illustrations and replaces them with reposts.
The name `fooroh` comes from the Japanese word `封蝋`, which means sealing wax.

## Requirements

Serverless Bluesky bot deployable on AWS via AWS CDK.
The application part is a Lambda function or ECS service written in python and deployed as a Docker container image.

**deploy target**

* AWS Account

**local development environment**

* AWS CLI
* Node.js ^18
* Python ^3.13
* Poetry ^2
* Docker Service

## quick start

```bash
$ npm install

# check
$ npx cdk bootstrap --profile default
$ npx cdk synth --profile default -c env=dev --all

# deploy each Stack
$ npx cdk deploy fooroh-CommonResourceStack-dev -c env=dev
$ npx cdk deploy fooroh-FollowFlowStack-dev -c env=dev
$ npx cdk deploy fooroh-SignupFlowStack-dev -c env=dev
$ npx cdk deploy fooroh-SetWatermarkImgStack-dev -c env=dev
$ npx cdk deploy fooroh-WatermarkingFlowStack-dev -c env=dev
$ npx cdk deploy fooroh-SignoutFlowStack-dev -c env=dev
$ npx cdk deploy fooroh-FirehoseStack-dev -c env=dev

# deploy all Stacks at once
$ npx cdk deploy --profile default -c env=dev --all
```

## Design

### follow
![follow](./docs/follow.drawio.svg)

### sign up
![signup](./docs/signup.drawio.svg)

### set watermark image
![set-watermark-image](./docs/set-watermark-image.drawio.svg)

### watermarking
![watermarking](./docs/watermarking.drawio.svg)

### sign out
![signout](./docs/signout.drawio.svg)
