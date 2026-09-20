#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STACK_NAME="${STACK_NAME:-opsrelay}"
AWS_REGION="${AWS_REGION:-ap-south-1}"

BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" --query "Stacks[0].Outputs[?OutputKey=='FrontendBucket'].OutputValue" --output text)
API_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)

cp frontend/config.example.js frontend/config.js
python3 - <<PY
from pathlib import Path
p=Path('frontend/config.js')
s=p.read_text().replace('REPLACE_WITH_API_URL','$API_URL')
p.write_text(s)
PY
aws s3 sync frontend/ "s3://$BUCKET/" --delete --region "$AWS_REGION"
cat <<OUT
Frontend deployed.
API: $API_URL
Bucket: $BUCKET
OUT
