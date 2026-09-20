#!/usr/bin/env pwsh
# OpsRelay AWS Infrastructure Provisioning Script
# Account: 704932818996 | Region: ap-south-1

$AWS = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$REGION = "ap-south-1"
$ACCOUNT = "704932818996"
$APP = "opsrelay"
$BUCKET = "opsrelay-frontend-$ACCOUNT"
$ROLE_NAME = "opsrelay-lambda-role"

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host "  OpsRelay AWS Infrastructure Provisioning" -ForegroundColor Cyan
Write-Host "  Account: $ACCOUNT | Region: $REGION" -ForegroundColor Cyan
Write-Host "=====================================================`n" -ForegroundColor Cyan

# ─────────────────────────────────────────────────────────
# STEP 1: IAM Role for Lambda
# ─────────────────────────────────────────────────────────
Write-Host "[1/8] Creating IAM Lambda Execution Role..." -ForegroundColor Yellow

$trustPolicy = @'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "lambda.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
'@

$trustFile = "$env:TEMP\trust-policy.json"
$trustPolicy | Out-File -FilePath $trustFile -Encoding utf8

try {
    $roleResult = & $AWS iam create-role `
        --role-name $ROLE_NAME `
        --assume-role-policy-document file://$trustFile `
        --region $REGION | ConvertFrom-Json
    $ROLE_ARN = $roleResult.Role.Arn
    Write-Host "  Created role: $ROLE_ARN" -ForegroundColor Green
} catch {
    $roleResult = & $AWS iam get-role --role-name $ROLE_NAME | ConvertFrom-Json
    $ROLE_ARN = $roleResult.Role.Arn
    Write-Host "  Role already exists: $ROLE_ARN" -ForegroundColor Green
}

# Attach managed policies
& $AWS iam attach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
& $AWS iam attach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
& $AWS iam attach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::aws:policy/AmazonSNSFullAccess
Write-Host "  Policies attached." -ForegroundColor Green

# ─────────────────────────────────────────────────────────
# STEP 2: DynamoDB Tables
# ─────────────────────────────────────────────────────────
Write-Host "`n[2/8] Creating DynamoDB Tables..." -ForegroundColor Yellow

$tables = @(
    @{ name = "opsrelay-machines";        key = "machine_id";    type = "S" },
    @{ name = "opsrelay-orders";          key = "order_id";      type = "S" },
    @{ name = "opsrelay-recommendations"; key = "rec_id";        type = "S" },
    @{ name = "opsrelay-alerts";          key = "alert_id";      type = "S" },
    @{ name = "opsrelay-telemetry";       key = "machine_id";    type = "S" }
)

foreach ($t in $tables) {
    try {
        & $AWS dynamodb create-table `
            --table-name $t.name `
            --attribute-definitions "AttributeName=$($t.key),AttributeType=$($t.type)" `
            --key-schema "AttributeName=$($t.key),KeyType=HASH" `
            --billing-mode PAY_PER_REQUEST `
            --region $REGION | Out-Null
        Write-Host "  Created table: $($t.name)" -ForegroundColor Green
    } catch {
        Write-Host "  Table already exists: $($t.name)" -ForegroundColor DarkGray
    }
}

# ─────────────────────────────────────────────────────────
# STEP 3: Seed DynamoDB with Sample Data
# ─────────────────────────────────────────────────────────
Write-Host "`n[3/8] Seeding DynamoDB with OpsRelay data..." -ForegroundColor Yellow

$machinesData = @(
    @{ machine_id = "M-001"; name = "Packaging Line A1"; status = "RUNNING"; health_score = "98"; location = "Plant 1 - Line A"; model = "PK-5000" },
    @{ machine_id = "M-002"; name = "Conveyor Belt B3";  status = "WARNING"; health_score = "72"; location = "Plant 1";           model = "CB-3000" },
    @{ machine_id = "M-003"; name = "Robot Arm C2";      status = "CRITICAL";health_score = "45"; location = "Plant 2";           model = "RA-7200" },
    @{ machine_id = "M-004"; name = "Cooling System D1"; status = "RUNNING"; health_score = "95"; location = "Plant 3";           model = "CS-2100" },
    @{ machine_id = "M-005"; name = "Assembly Unit E5";  status = "RUNNING"; health_score = "89"; location = "Plant 3";           model = "AU-4500" }
)

foreach ($m in $machinesData) {
    & $AWS dynamodb put-item `
        --table-name "opsrelay-machines" `
        --item "{`"machine_id`":{`"S`":`"$($m.machine_id)`"},`"name`":{`"S`":`"$($m.name)`"},`"status`":{`"S`":`"$($m.status)`"},`"health_score`":{`"N`":`"$($m.health_score)`"},`"location`":{`"S`":`"$($m.location)`"},`"model`":{`"S`":`"$($m.model)`"}}" `
        --region $REGION | Out-Null
}
Write-Host "  5 machines seeded." -ForegroundColor Green

$ordersData = @(
    @{ order_id = "ORD-00123"; customer = "Acme Corp";      status = "IN_TRANSIT"; destination = "New York";    risk_score = "12" },
    @{ order_id = "ORD-00124"; customer = "Global Inc";     status = "DELAYED";    destination = "Los Angeles"; risk_score = "51" },
    @{ order_id = "ORD-00125"; customer = "Tech Solutions"; status = "DELAYED";    destination = "Chicago, IL"; risk_score = "72" },
    @{ order_id = "ORD-00126"; customer = "Retail Plus";    status = "IN_TRANSIT"; destination = "Miami";       risk_score = "25" },
    @{ order_id = "ORD-00127"; customer = "Manufacturing Co";status = "DELIVERED"; destination = "Dallas";      risk_score = "8"  }
)

foreach ($o in $ordersData) {
    & $AWS dynamodb put-item `
        --table-name "opsrelay-orders" `
        --item "{`"order_id`":{`"S`":`"$($o.order_id)`"},`"customer`":{`"S`":`"$($o.customer)`"},`"status`":{`"S`":`"$($o.status)`"},`"destination`":{`"S`":`"$($o.destination)`"},`"risk_score`":{`"N`":`"$($o.risk_score)`"}}" `
        --region $REGION | Out-Null
}
Write-Host "  5 orders seeded." -ForegroundColor Green

# ─────────────────────────────────────────────────────────
# STEP 4: S3 Bucket for Frontend
# ─────────────────────────────────────────────────────────
Write-Host "`n[4/8] Creating S3 Bucket for Frontend Hosting..." -ForegroundColor Yellow

try {
    & $AWS s3api create-bucket `
        --bucket $BUCKET `
        --region $REGION `
        --create-bucket-configuration LocationConstraint=$REGION | Out-Null
    Write-Host "  Created bucket: s3://$BUCKET" -ForegroundColor Green
} catch {
    Write-Host "  Bucket already exists: s3://$BUCKET" -ForegroundColor DarkGray
}

# Disable block public access for static website hosting
& $AWS s3api put-public-access-block `
    --bucket $BUCKET `
    --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false" | Out-Null

# Enable static website hosting
& $AWS s3 website s3://$BUCKET/ --index-document index.html --error-document index.html | Out-Null

# Bucket policy for public read
$bucketPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadGetObject",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::$BUCKET/*"
  }]
}
"@
$bucketPolicy | Out-File -FilePath "$env:TEMP\bucket-policy.json" -Encoding utf8
& $AWS s3api put-bucket-policy --bucket $BUCKET --policy file://$env:TEMP/bucket-policy.json | Out-Null
Write-Host "  Static website hosting enabled." -ForegroundColor Green

# ─────────────────────────────────────────────────────────
# STEP 5: Upload Frontend to S3
# ─────────────────────────────────────────────────────────
Write-Host "`n[5/8] Uploading Frontend to S3..." -ForegroundColor Yellow

$frontendPath = "d:\DownLoads\opsrelay-complete\opsrelay-complete\frontend"
& $AWS s3 sync $frontendPath s3://$BUCKET/ `
    --region $REGION `
    --acl public-read `
    --delete | Out-Null

Write-Host "  Frontend uploaded to S3." -ForegroundColor Green
$S3_URL = "http://$BUCKET.s3-website.$REGION.amazonaws.com"
Write-Host "  S3 Website URL: $S3_URL" -ForegroundColor Cyan

# ─────────────────────────────────────────────────────────
# STEP 6: Package and Deploy Lambda Backend
# ─────────────────────────────────────────────────────────
Write-Host "`n[6/8] Packaging Lambda Function..." -ForegroundColor Yellow

$lambdaDir = "$env:TEMP\opsrelay-lambda"
New-Item -ItemType Directory -Force -Path $lambdaDir | Out-Null

# Write Lambda handler
@'
import json
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

def cors_response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "Content-Type": "application/json"
        },
        "body": json.dumps(body, cls=DecimalEncoder)
    }

def handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")

    if method == "OPTIONS":
        return cors_response(200, {})

    try:
        if path == "/api/dashboard" or path == "/api/dashboard/":
            machines_table = dynamodb.Table("opsrelay-machines")
            orders_table   = dynamodb.Table("opsrelay-orders")
            alerts_table   = dynamodb.Table("opsrelay-alerts")
            recs_table     = dynamodb.Table("opsrelay-recommendations")

            machines = machines_table.scan().get("Items", [])
            orders   = orders_table.scan().get("Items", [])
            alerts   = alerts_table.scan().get("Items", [])
            recs     = recs_table.scan().get("Items", [])

            healthy  = sum(1 for m in machines if m.get("status") == "RUNNING")
            warning  = sum(1 for m in machines if m.get("status") == "WARNING")
            critical = sum(1 for m in machines if m.get("status") == "CRITICAL")

            return cors_response(200, {
                "machines":        machines,
                "orders":          orders,
                "alerts":          alerts,
                "recommendations": recs,
                "kpis": {
                    "total_machines":    len(machines),
                    "active_alerts":     len(alerts),
                    "orders_in_transit": sum(1 for o in orders if o.get("status") == "IN_TRANSIT"),
                    "on_time_delivery":  96.8,
                    "healthy_machines":  healthy,
                    "warning_machines":  warning,
                    "critical_machines": critical
                }
            })

        elif path.startswith("/api/machines"):
            table = dynamodb.Table("opsrelay-machines")
            if method == "GET":
                parts = path.rstrip("/").split("/")
                if len(parts) >= 4 and parts[3]:
                    result = table.get_item(Key={"machine_id": parts[3]})
                    item = result.get("Item")
                    if item:
                        return cors_response(200, item)
                    return cors_response(404, {"error": "Machine not found"})
                return cors_response(200, table.scan().get("Items", []))
            elif method == "POST":
                body = json.loads(event.get("body", "{}"))
                table.put_item(Item=body)
                return cors_response(201, body)

        elif path.startswith("/api/orders"):
            table = dynamodb.Table("opsrelay-orders")
            if method == "GET":
                parts = path.rstrip("/").split("/")
                if len(parts) >= 4 and parts[3]:
                    result = table.get_item(Key={"order_id": parts[3]})
                    item = result.get("Item")
                    if item:
                        return cors_response(200, item)
                    return cors_response(404, {"error": "Order not found"})
                return cors_response(200, table.scan().get("Items", []))
            elif method == "POST":
                body = json.loads(event.get("body", "{}"))
                table.put_item(Item=body)
                return cors_response(201, body)

        elif path.startswith("/api/recommendations"):
            table = dynamodb.Table("opsrelay-recommendations")
            return cors_response(200, table.scan().get("Items", []))

        return cors_response(404, {"error": f"Route not found: {method} {path}"})

    except Exception as e:
        print(f"ERROR: {e}")
        return cors_response(500, {"error": str(e)})
'@ | Out-File -FilePath "$lambdaDir\lambda_function.py" -Encoding utf8

# Zip it
Compress-Archive -Path "$lambdaDir\lambda_function.py" -DestinationPath "$env:TEMP\opsrelay-api.zip" -Force
Write-Host "  Lambda package ready." -ForegroundColor Green

# Wait for IAM role propagation
Write-Host "  Waiting 10s for IAM role propagation..." -ForegroundColor DarkGray
Start-Sleep -Seconds 10

# Deploy Lambda
try {
    $lambdaResult = & $AWS lambda create-function `
        --function-name "opsrelay-api" `
        --runtime "python3.12" `
        --role $ROLE_ARN `
        --handler "lambda_function.handler" `
        --zip-file "fileb://$env:TEMP\opsrelay-api.zip" `
        --timeout 30 `
        --memory-size 256 `
        --region $REGION | ConvertFrom-Json
    $LAMBDA_ARN = $lambdaResult.FunctionArn
    Write-Host "  Lambda created: $LAMBDA_ARN" -ForegroundColor Green
} catch {
    & $AWS lambda update-function-code `
        --function-name "opsrelay-api" `
        --zip-file "fileb://$env:TEMP\opsrelay-api.zip" `
        --region $REGION | Out-Null
    $lambdaResult = & $AWS lambda get-function --function-name "opsrelay-api" --region $REGION | ConvertFrom-Json
    $LAMBDA_ARN = $lambdaResult.Configuration.FunctionArn
    Write-Host "  Lambda updated: $LAMBDA_ARN" -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────
# STEP 7: API Gateway
# ─────────────────────────────────────────────────────────
Write-Host "`n[7/8] Creating API Gateway..." -ForegroundColor Yellow

$apiResult = & $AWS apigateway create-rest-api `
    --name "opsrelay-api-gw" `
    --description "OpsRelay Factory Intelligence API" `
    --region $REGION | ConvertFrom-Json
$API_ID = $apiResult.id
Write-Host "  API Gateway created: $API_ID" -ForegroundColor Green

# Get root resource
$rootResult = & $AWS apigateway get-resources --rest-api-id $API_ID --region $REGION | ConvertFrom-Json
$ROOT_ID = ($rootResult.items | Where-Object { $_.path -eq "/" }).id

# Create {proxy+} resource
$proxyResource = & $AWS apigateway create-resource `
    --rest-api-id $API_ID `
    --parent-id $ROOT_ID `
    --path-part "{proxy+}" `
    --region $REGION | ConvertFrom-Json
$PROXY_ID = $proxyResource.id

# Create ANY method on proxy
& $AWS apigateway put-method `
    --rest-api-id $API_ID `
    --resource-id $PROXY_ID `
    --http-method ANY `
    --authorization-type NONE `
    --region $REGION | Out-Null

# Create ANY method on root
& $AWS apigateway put-method `
    --rest-api-id $API_ID `
    --resource-id $ROOT_ID `
    --http-method ANY `
    --authorization-type NONE `
    --region $REGION | Out-Null

# Integration for proxy resource
& $AWS apigateway put-integration `
    --rest-api-id $API_ID `
    --resource-id $PROXY_ID `
    --http-method ANY `
    --type AWS_PROXY `
    --integration-http-method POST `
    --uri "arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" `
    --region $REGION | Out-Null

# Integration for root resource
& $AWS apigateway put-integration `
    --rest-api-id $API_ID `
    --resource-id $ROOT_ID `
    --http-method ANY `
    --type AWS_PROXY `
    --integration-http-method POST `
    --uri "arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" `
    --region $REGION | Out-Null

# Deploy API
& $AWS apigateway create-deployment `
    --rest-api-id $API_ID `
    --stage-name prod `
    --region $REGION | Out-Null

# Add Lambda permission for API Gateway invoke
& $AWS lambda add-permission `
    --function-name "opsrelay-api" `
    --statement-id "apigateway-invoke" `
    --action "lambda:InvokeFunction" `
    --principal "apigateway.amazonaws.com" `
    --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT}:${API_ID}/*/*" `
    --region $REGION | Out-Null

$API_URL = "https://$API_ID.execute-api.$REGION.amazonaws.com/prod"
Write-Host "  API Gateway deployed: $API_URL" -ForegroundColor Cyan

# ─────────────────────────────────────────────────────────
# STEP 8: SNS for Alerts
# ─────────────────────────────────────────────────────────
Write-Host "`n[8/8] Creating SNS Alert Topic..." -ForegroundColor Yellow

$snsResult = & $AWS sns create-topic `
    --name "opsrelay-alerts" `
    --region $REGION | ConvertFrom-Json
$SNS_ARN = $snsResult.TopicArn
Write-Host "  SNS topic: $SNS_ARN" -ForegroundColor Green

# ─────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────
Write-Host "`n=====================================================" -ForegroundColor Green
Write-Host "  OpsRelay AWS Infrastructure — COMPLETE" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Account      : $ACCOUNT" -ForegroundColor White
Write-Host "  Region       : $REGION (Mumbai)" -ForegroundColor White
Write-Host ""
Write-Host "  API Gateway  : $API_URL" -ForegroundColor Cyan
Write-Host "  S3 Website   : $S3_URL" -ForegroundColor Cyan
Write-Host "  Lambda       : opsrelay-api (Python 3.12)" -ForegroundColor Cyan
Write-Host "  DynamoDB     : 5 tables" -ForegroundColor Cyan
Write-Host "  SNS          : opsrelay-alerts" -ForegroundColor Cyan
Write-Host ""

# Write API URL to config file for frontend
$configContent = "window.OPSR_CONFIG = { apiBaseUrl: '$API_URL/api' };"
$configPath = Join-Path "d:" "DownLoads\opsrelay-complete\opsrelay-complete\frontend\config.js"
$configContent | Out-File -FilePath $configPath -Encoding utf8
Write-Host "  config.js updated with live API URL." -ForegroundColor Green

# Re-sync frontend with updated config
$frontendSrc = Join-Path "d:" "DownLoads\opsrelay-complete\opsrelay-complete\frontend"
& $AWS s3 sync $frontendSrc "s3://$BUCKET/" `
    --region $REGION `
    --acl public-read | Out-Null
Write-Host "  Frontend re-uploaded with production API config." -ForegroundColor Green
Write-Host ""
Write-Host "  OPEN IN BROWSER: $S3_URL" -ForegroundColor Yellow
Write-Host "=====================================================" -ForegroundColor Green
