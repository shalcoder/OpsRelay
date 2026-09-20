# Ship It deployment

## 1. Prerequisites

Install:

- AWS CLI
- AWS SAM CLI
- Python 3.12+
- Docker 24+

Authenticate using your normal AWS profile/SSO. Static keys are not required by the application. `.env.example` contains key placeholders only because some teams use environment variables.

## 2. Deploy serverless core

```bash
export AWS_REGION=ap-south-1
export STACK_NAME=opsrelay
bash scripts/deploy.sh
```

The stack creates API Gateway, Lambda functions, DynamoDB, S3 raw-event storage, S3 static frontend hosting, EventBridge, SQS + DLQ, and a CloudWatch dashboard.

## 3. Create the SageMaker predictor

Create or identify an IAM execution role trusted by `sagemaker.amazonaws.com` with access to read the model artifact bucket and pull the ECR image. Set:

```bash
export SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>
export SAGEMAKER_ENDPOINT_NAME=opsrelay-predictor
```

Then:

```bash
bash scripts/deploy_sagemaker.sh
```

The script trains the included model, packages it, creates/uses ECR, pushes the inference image, creates a SageMaker AI model, a serverless endpoint configuration, and the endpoint. The API invokes the endpoint with the SageMaker Runtime `InvokeEndpoint` API when `SAGEMAKER_ENABLED=true`.

## 4. Turn on cloud intelligence

Redeploy SAM with:

```bash
sam deploy --stack-name "$STACK_NAME" --region "$AWS_REGION" --capabilities CAPABILITY_IAM --resolve-s3 \
  --parameter-overrides \
  CorsOrigins='*' \
  SageMakerEnabled=true \
  SageMakerEndpointName=opsrelay-predictor \
  StrandsEnabled=true \
  BedrockModelId=amazon.nova-lite-v1:0
```

Strands runs inside the Lambda process; the default model provider is Amazon Bedrock. The API Lambda needs permission to use the selected model. Add the least-privilege Bedrock invoke policy for the model you choose before enabling `StrandsEnabled`.

## 5. Publish the frontend

```bash
bash scripts/deploy_frontend.sh
```

The script reads the API URL from CloudFormation, writes `frontend/config.js`, and syncs the UI to the provisioned S3 website bucket.

## Notes

- SageMaker serverless inference avoids a permanently running instance, but it is still billable and should be shut down after the hackathon.
- The included ML dataset is synthetic/demo data. Replace it with plant history before production use.
- The deterministic risk engine remains authoritative for the operational score. ML contributes prediction signals; the agent explains and orchestrates actions.
