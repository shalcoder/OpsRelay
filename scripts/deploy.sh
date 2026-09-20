#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${AWS_REGION:=ap-south-1}"
: "${STACK_NAME:=opsrelay}"

if ! command -v sam >/dev/null 2>&1; then echo "AWS SAM CLI is required."; exit 1; fi
if ! command -v aws >/dev/null 2>&1; then echo "AWS CLI is required."; exit 1; fi

sam build -t infra/template.yaml
sam deploy --stack-name "$STACK_NAME" --region "$AWS_REGION" --capabilities CAPABILITY_IAM --resolve-s3 --parameter-overrides "CorsOrigins=*"

aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" --query 'Stacks[0].Outputs' --output table
