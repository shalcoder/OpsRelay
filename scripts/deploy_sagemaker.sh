#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REGION="${AWS_REGION:-ap-south-1}"
ROLE_ARN="${SAGEMAKER_EXECUTION_ROLE_ARN:-arn:aws:iam::<ACCOUNT_ID>:role/<SAGEMAKER_EXECUTION_ROLE>}"
MEMORY="${SAGEMAKER_ENDPOINT_MEMORY_MB:-2048}"
CONCURRENCY="${SAGEMAKER_MAX_CONCURRENCY:-1}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REPO="${SAGEMAKER_ECR_REPO:-opsrelay-predictor}"
BUCKET="${SAGEMAKER_MODEL_BUCKET:-opsrelay-models-${ACCOUNT_ID}-${REGION}}"
ENDPOINT="${SAGEMAKER_ENDPOINT_NAME:-opsrelay-predictor}"
IMAGE="${SAGEMAKER_IMAGE_URI:-${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:latest}"

if [[ "$ROLE_ARN" == *"<ACCOUNT_ID>"* || "$ROLE_ARN" == *"<SAGEMAKER_EXECUTION_ROLE>"* ]]; then
  echo "Set SAGEMAKER_EXECUTION_ROLE_ARN in your environment/.env before running this script."; exit 1
fi

aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
docker build -t "$REPO:latest" ml/serve
docker tag "$REPO:latest" "$IMAGE"
docker push "$IMAGE"

aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null 2>&1 || aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
python3 ml/train.py --output ml/artifacts/model.joblib
mkdir -p ml/artifacts/package
cp ml/artifacts/model.joblib ml/artifacts/package/model.joblib
tar -C ml/artifacts/package -czf ml/artifacts/model.tar.gz model.joblib
aws s3 cp ml/artifacts/model.tar.gz "s3://$BUCKET/opsrelay/model.tar.gz" --region "$REGION"

python3 scripts/provision_sagemaker_endpoint.py \
  --region "$REGION" \
  --role-arn "$ROLE_ARN" \
  --image-uri "$IMAGE" \
  --model-data-url "s3://$BUCKET/opsrelay/model.tar.gz" \
  --endpoint-name "$ENDPOINT" \
  --memory "$MEMORY" \
  --max-concurrency "$CONCURRENCY"

echo "SageMaker endpoint ready: $ENDPOINT"
