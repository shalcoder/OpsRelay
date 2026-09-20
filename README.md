# OpsRelay

## Zero-ERP Factory Execution Copilot

OpsRelay is an event-driven manufacturing operations system that turns shop-floor signals into evidence-backed delivery-risk assessments and human-approved recovery actions.

**Promise loop:** Signal → Evidence → Risk → Action → Recovery

### What is implemented

- Static operations control center with Overview, Promise Board, Signal Stream, Operations Agent, Recovery Queue, Audit Trail.
- Real event ingestion API.
- Local JSON persistence and AWS DynamoDB persistence.
- EventBridge → SQS → Lambda processing path in the cloud.
- Raw event archival to S3.
- Real SageMaker AI Runtime integration through `InvokeEndpoint`.
- Included trainable ML model and custom SageMaker inference container.
- Deterministic operational risk engine.
- Strands Agents integration using Amazon Bedrock when enabled.
- Grounded agent tools for orders, machines, events, quality, risk, and capacity.
- Human approval gate before recovery action execution.
- Action execution simulator that reassigns a production order to an available compatible machine.
- Audit trail.
- CloudWatch dashboard.
- Cognito user pool/client provisioned for authentication integration.
- Live frontend login via Cognito `USER_PASSWORD_AUTH`, with evaluator demo access buttons.
- AWS SAM infrastructure.
- Local Docker runtime.
- Tests for risk calculation and end-to-end recovery flow.
- Mermaid architecture/UML diagrams and submission documentation.

## Repository structure

```text
opsrelay/
├── api/
│   ├── core/
│   │   ├── agent.py
│   │   ├── predictor.py
│   │   ├── risk.py
│   │   ├── service.py
│   │   └── store.py
│   ├── lambda_api.py
│   ├── lambda_ingest.py
│   ├── lambda_processor.py
│   ├── local_server.py
│   ├── requirements.txt
│   └── tests/
├── frontend/
├── data/
├── docs/
├── infra/
├── local/
├── ml/
├── scripts/
├── .env.example
├── Makefile
└── README.md
```

## Run locally

### Option A — Python

Python 3.12+ is recommended.

```bash
python3 -m pip install -r requirements.txt
bash run_local.sh
```

Open `http://localhost:8080`.

### Option B — Windows PowerShell

```powershell
python -m pip install -r requirements.txt
.\run_local.ps1
```

### Option C — Docker

```bash
docker compose -f local/docker-compose.yml up --build
```

Open `http://localhost:8080`.

The local application works without an AWS account. It uses the deterministic predictor fallback and the deterministic agent fallback until cloud intelligence is enabled.

### Live dashboard access

The deployed frontend supports real Cognito sign-in using the configured user pool. The provisioning script can create evaluator accounts and assign their groups. Supply the shared password through the local `OPSR_DEMO_PASSWORD` environment variable; credentials are intentionally not stored in this repository.

```text
judge@opsrelay.com    Supervisor
manager@opsrelay.com  OperationsManager
analyst@opsrelay.com  Analyst
```

Normal sign-in stores the Cognito access token and sends it as a bearer token to the API.

## Cloud deployment

Read `docs/cloud.md`.

The required cloud placeholders are intentionally isolated in environment variables / CloudFormation parameters:

```text
AWS credentials / profile
SAGEMAKER_EXECUTION_ROLE_ARN
SAGEMAKER_ENDPOINT_NAME
BEDROCK_MODEL_ID
```

The application itself contains no hard-coded secret keys.

### Serverless core

```bash
export AWS_REGION=ap-south-1
export STACK_NAME=opsrelay
bash scripts/deploy.sh
```

### SageMaker AI

```bash
export SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>
export SAGEMAKER_ENDPOINT_NAME=opsrelay-predictor
bash scripts/deploy_sagemaker.sh
```

The model is trained locally from the included demo generator, packaged, uploaded to S3, the inference container is built/pushed to ECR, and a SageMaker AI serverless endpoint is created.

### Enable SageMaker + Strands

```bash
sam deploy --stack-name "$STACK_NAME" --region "$AWS_REGION" --capabilities CAPABILITY_IAM --resolve-s3 \
  --parameter-overrides \
  CorsOrigins='*' \
  SageMakerEnabled=true \
  SageMakerEndpointName=opsrelay-predictor \
  StrandsEnabled=true \
  BedrockModelId=apac.amazon.nova-lite-v1:0
```

Then deploy the frontend:

```bash
bash scripts/deploy_frontend.sh
```

## Event examples

POST `/api/events` locally or `/prod/events` through API Gateway:

```json
{
  "orderId": "ORD-1048",
  "machineId": "CNC-04",
  "type": "MACHINE_STOP",
  "durationMinutes": 25,
  "description": "Coolant pressure low; machine stopped."
}
```

The cloud flow is:

```text
POST /events
   ↓
API Gateway
   ↓
Ingestion Lambda
   ├── DynamoDB
   ├── S3 raw event
   └── EventBridge
          ↓
        SQS
          ↓
   Processor Lambda
          ↓
    SageMaker AI
          ↓
    Risk Engine
          ↓
      DynamoDB
```

## AI responsibility boundaries

**SageMaker AI** predicts delay/failure/anomaly signals.

**Risk Engine** calculates the authoritative operational risk score.

**Strands Agent** investigates evidence and produces a recommendation.

**Human Approval** is required for consequential recovery actions.

**Action Service** performs the simulated operational change and records it.

This boundary avoids making the LLM responsible for a numeric operational control score.

## Important demo limitation

The included dataset and action executor are a realistic simulation. They are designed to demonstrate the complete software workflow without requiring a live factory MES/PLC. Replace the adapters with plant-specific connectors for production deployment.

## Competition hygiene

For a First Commit submission, initialize the Git repository and make the first commit only after the hackathon clock permits new project work. Do not import old project history into this repository.
