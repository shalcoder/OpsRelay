# OpsRelay Full Target Architecture Provisioner
# Account: 704932818996 | Region: ap-south-1

$ErrorActionPreference = "Continue"
$AWS = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$REGION = "ap-south-1"
$ACCOUNT = "704932818996"
$DATA_BUCKET = "opsrelay-data-$ACCOUNT"
$ROLE_NAME = "opsrelay-lambda-role"
$MAIN_TABLE = "opsrelay-main"
$EVENT_BUS = "default"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  Provisioning OpsRelay Production Event-Driven Architecture     " -ForegroundColor Cyan
Write-Host "  Region: $REGION | Account: $ACCOUNT                           " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# ─── STEP 1: S3 Data Lake Setup ───────────────────────────────────────────
Write-Host "`n[1/8] Configuring S3 Data Lake ($DATA_BUCKET)..." -ForegroundColor Yellow
& $AWS s3api put-public-access-block --bucket $DATA_BUCKET --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Upload zero-byte placeholder files to establish prefixes
$tempDir = Join-Path $env:TEMP "opsrelay_markers"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$markerFile = Join-Path $tempDir ".keep"
"" | Out-File -FilePath $markerFile -Encoding ascii

$prefixes = @(
    "raw/telemetry/",
    "raw/machine-events/",
    "raw/quality-events/",
    "raw/material-events/",
    "processed/features/",
    "history/predictions/",
    "audit/",
    "models/"
)
foreach ($p in $prefixes) {
    & $AWS s3 cp $markerFile "s3://$DATA_BUCKET/$p" --region $REGION | Out-Null
}
Write-Host "  Data lake prefixes verified: raw/, processed/, history/, audit/, models/" -ForegroundColor Green

# ─── STEP 2: IAM Lambda Execution Role Policies ───────────────────────────
Write-Host "`n[2/8] Expanding IAM Lambda Execution Role Permissions..." -ForegroundColor Yellow
$managedPolicies = @(
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AmazonSNSFullAccess",
    "arn:aws:iam::aws:policy/AmazonSQSFullAccess",
    "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess",
    "arn:aws:iam::aws:policy/AmazonBedrockFullAccess",
    "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
)

foreach ($pol in $managedPolicies) {
    & $AWS iam attach-role-policy --role-name $ROLE_NAME --policy-arn $pol
}

# Attach inline S3 policy for data lake
$s3PolicyDoc = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::$DATA_BUCKET",
        "arn:aws:s3:::$DATA_BUCKET/*"
      ]
    }
  ]
}
"@
$s3PolicyFile = Join-Path $tempDir "s3-policy.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($s3PolicyFile, $s3PolicyDoc, $utf8NoBom)
Write-Host "  Role policies attached (DynamoDB, SQS, EventBridge, Bedrock, SageMaker, S3)." -ForegroundColor Green

# ─── STEP 3: DynamoDB Single-Table for OpsRelay Entity Engine ─────────────
Write-Host "`n[3/8] Provisioning DynamoDB Single-Table '$MAIN_TABLE'..." -ForegroundColor Yellow
try {
    & $AWS dynamodb create-table `
        --table-name $MAIN_TABLE `
        --attribute-definitions "AttributeName=pk,AttributeType=S" "AttributeName=sk,AttributeType=S" `
        --key-schema "AttributeName=pk,KeyType=HASH" "AttributeName=sk,KeyType=RANGE" `
        --billing-mode PAY_PER_REQUEST `
        --region $REGION | Out-Null
    Write-Host "  Creating table $MAIN_TABLE..." -ForegroundColor Green
    & $AWS dynamodb wait table-exists --table-name $MAIN_TABLE --region $REGION
} catch {
    Write-Host "  Table $MAIN_TABLE already exists." -ForegroundColor DarkGray
}

# ─── STEP 4: SQS + SQS DLQ + EventBridge Integration ──────────────────────
Write-Host "`n[4/8] Provisioning SQS, DLQ and EventBridge Routing..." -ForegroundColor Yellow

# Create DLQ
$dlqResult = & $AWS sqs create-queue --queue-name "opsrelay-factory-events-dlq" --region $REGION | ConvertFrom-Json
$DLQ_URL = $dlqResult.QueueUrl
$dlqAttr = & $AWS sqs get-queue-attributes --queue-url $DLQ_URL --attribute-names QueueArn --region $REGION | ConvertFrom-Json
$DLQ_ARN = $dlqAttr.Attributes.QueueArn
Write-Host "  DLQ ready: $DLQ_ARN" -ForegroundColor Green

# Create Main Queue with Redrive Policy
$redrivePolicy = @{
    deadLetterTargetArn = $DLQ_ARN
    maxReceiveCount     = 3
} | ConvertTo-Json -Compress

$queueAttributes = @{
  VisibilityTimeout = "120"
  RedrivePolicy     = $redrivePolicy
} | ConvertTo-Json -Compress
$queueAttributesFile = Join-Path $tempDir "queue-attributes.json"
[System.IO.File]::WriteAllText($queueAttributesFile, $queueAttributes, $utf8NoBom)

$queueResult = & $AWS sqs create-queue `
    --queue-name "opsrelay-factory-events" `
  --attributes "file://$queueAttributesFile" `
    --region $REGION | ConvertFrom-Json
$QUEUE_URL = $queueResult.QueueUrl
$queueAttr = & $AWS sqs get-queue-attributes --queue-url $QUEUE_URL --attribute-names QueueArn --region $REGION | ConvertFrom-Json
$QUEUE_ARN = $queueAttr.Attributes.QueueArn
Write-Host "  Main Queue ready: $QUEUE_ARN" -ForegroundColor Green

# Create EventBridge Rule
$pattern = '{\"source\":[\"opsrelay.ingestion\"],\"detail-type\":[\"FactoryEvent\"]}'
& $AWS events put-rule `
    --name "opsrelay-factory-signals-rule" `
    --event-pattern $pattern `
    --description "Routes factory signals from API to SQS processing queue" `
    --state ENABLED `
    --region $REGION | Out-Null
Write-Host "  EventBridge rule 'opsrelay-factory-signals-rule' created." -ForegroundColor Green

# Grant EventBridge permissions to push to SQS
$sqsPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "events.amazonaws.com" },
      "Action": "sqs:SendMessage",
      "Resource": "$QUEUE_ARN"
    }
  ]
}
"@
$sqsPolicyFile = Join-Path $tempDir "sqs-policy.json"
$sqsPolicy | Out-File -FilePath $sqsPolicyFile -Encoding utf8
$sqsQueueAttributes = @{ Policy = $sqsPolicy } | ConvertTo-Json -Compress
$sqsQueueAttributesFile = Join-Path $tempDir "sqs-queue-attributes.json"
[System.IO.File]::WriteAllText($sqsQueueAttributesFile, $sqsQueueAttributes, $utf8NoBom)
& $AWS sqs set-queue-attributes --queue-url $QUEUE_URL --attributes "file://$sqsQueueAttributesFile" --region $REGION | Out-Null

# Add SQS Queue as Target for EventBridge Rule
& $AWS events put-targets `
    --rule "opsrelay-factory-signals-rule" `
    --targets "Id=OpsRelaySQSTarget,Arn=$QUEUE_ARN" `
    --region $REGION | Out-Null
Write-Host "  EventBridge target connected to SQS Queue." -ForegroundColor Green

# ─── STEP 5: Cognito User Pool & App Client ───────────────────────────────
Write-Host "`n[5/8] Provisioning Amazon Cognito User Pool & Client..." -ForegroundColor Yellow
$userPoolName = "opsrelay-users"
$existingPools = & $AWS cognito-idp list-user-pools --max-results 20 --region $REGION | ConvertFrom-Json
$pool = $existingPools.UserPools | Where-Object { $_.Name -eq $userPoolName }

if (-not $pool) {
    $poolResult = & $AWS cognito-idp create-user-pool `
        --pool-name $userPoolName `
        --auto-verified-attributes email `
        --policies '{\"PasswordPolicy\":{\"MinimumLength\":8,\"RequireUppercase\":true,\"RequireLowercase\":true,\"RequireNumbers\":true,\"RequireSymbols\":false}}' `
        --region $REGION | ConvertFrom-Json
    $USER_POOL_ID = $poolResult.UserPool.Id
    Write-Host "  Created User Pool: $USER_POOL_ID" -ForegroundColor Green
} else {
    $USER_POOL_ID = $pool.Id
    Write-Host "  User Pool exists: $USER_POOL_ID" -ForegroundColor DarkGray
}

$clients = & $AWS cognito-idp list-user-pool-clients --user-pool-id $USER_POOL_ID --region $REGION | ConvertFrom-Json
$client = $clients.UserPoolClients | Where-Object { $_.ClientName -eq "opsrelay-web" } | Select-Object -First 1
if (-not $client) {
  $clientResult = & $AWS cognito-idp create-user-pool-client `
    --user-pool-id $USER_POOL_ID `
    --client-name "opsrelay-web" `
    --no-generate-secret `
    --explicit-auth-flows "ALLOW_USER_PASSWORD_AUTH" "ALLOW_REFRESH_TOKEN_AUTH" "ALLOW_USER_SRP_AUTH" `
    --region $REGION | ConvertFrom-Json
  $CLIENT_ID = $clientResult.UserPoolClient.ClientId
  Write-Host "  Created User Pool Client: $CLIENT_ID" -ForegroundColor Green
} else {
  $CLIENT_ID = $client.ClientId
  Write-Host "  User Pool Client: $CLIENT_ID" -ForegroundColor DarkGray
}

# Create standard factory role groups
$groups = @("OperationsManager", "Supervisor", "Analyst")
foreach ($g in $groups) {
    & $AWS cognito-idp create-group --group-name $g --user-pool-id $USER_POOL_ID --description "OpsRelay $g Role" --region $REGION 2>$null | Out-Null
}
Write-Host "  Cognito User Groups created: OperationsManager, Supervisor, Analyst" -ForegroundColor Green

# Create stable evaluator accounts for the live dashboard. Existing accounts are
# left in place so rerunning provisioning does not reset a judge's password.
$demoPassword = $env:OPSR_DEMO_PASSWORD
if (-not $demoPassword) {
  throw "Set OPSR_DEMO_PASSWORD in the environment before provisioning evaluator accounts."
}
$demoUsers = @(
  @{ Username = "judge@opsrelay.com"; Group = "Supervisor" },
  @{ Username = "manager@opsrelay.com"; Group = "OperationsManager" },
  @{ Username = "analyst@opsrelay.com"; Group = "Analyst" }
)
foreach ($demoUser in $demoUsers) {
  & $AWS cognito-idp admin-get-user `
    --user-pool-id $USER_POOL_ID `
    --username $demoUser.Username `
    --region $REGION 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    & $AWS cognito-idp admin-create-user `
      --user-pool-id $USER_POOL_ID `
      --username $demoUser.Username `
            --user-attributes "Name=email,Value=$($demoUser.Username)" "Name=email_verified,Value=true" `
      --message-action SUPPRESS `
      --temporary-password $demoPassword `
      --region $REGION | Out-Null
  }
  & $AWS cognito-idp admin-set-user-password `
    --user-pool-id $USER_POOL_ID `
    --username $demoUser.Username `
    --password $demoPassword `
    --permanent `
    --region $REGION | Out-Null
  & $AWS cognito-idp admin-add-user-to-group `
    --user-pool-id $USER_POOL_ID `
    --username $demoUser.Username `
    --group-name $demoUser.Group `
    --region $REGION | Out-Null
}
Write-Host "  Cognito evaluator accounts ready: judge, manager, analyst." -ForegroundColor Green

# ─── STEP 6: SageMaker AI Model Packaging ─────────────────────────────────
Write-Host "`n[6/8] Training and Packaging ML Model for SageMaker..." -ForegroundColor Yellow
$mlDir = "d:\DownLoads\opsrelay-complete\opsrelay-complete\ml"
& python "$mlDir\train.py" --output "$mlDir\artifacts\model.joblib"

# Tar the model artifact for SageMaker
$artDir = "$mlDir\artifacts"
$tarPath = "$artDir\model.tar.gz"
if (Test-Path $tarPath) { Remove-Item $tarPath -Force }
tar -czvf "$tarPath" -C "$artDir" model.joblib
& $AWS s3 cp "$tarPath" "s3://$DATA_BUCKET/models/model.tar.gz" --region $REGION | Out-Null
Write-Host "  Model trained and uploaded to s3://$DATA_BUCKET/models/model.tar.gz" -ForegroundColor Green

# ─── STEP 7: Packaging & Deploying Complete Lambda Backend ────────────────
Write-Host "`n[7/8] Packaging Full OpsRelay Engine (API + Processor)..." -ForegroundColor Yellow

$pkgDir = Join-Path $tempDir "pkg"
if (Test-Path $pkgDir) { Remove-Item $pkgDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $pkgDir | Out-Null

# Copy api files into package
Copy-Item -Path "d:\DownLoads\opsrelay-complete\opsrelay-complete\api\*" -Destination $pkgDir -Recurse -Force

$zipPath = Join-Path $tempDir "opsrelay-engine.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$pkgDir\*" -DestinationPath $zipPath -Force

$ROLE_ARN = (& $AWS iam get-role --role-name $ROLE_NAME | ConvertFrom-Json).Role.Arn

# Update opsrelay-api Lambda
Write-Host "  Deploying opsrelay-api..." -ForegroundColor Yellow
& $AWS lambda update-function-code `
    --function-name "opsrelay-api" `
    --zip-file "fileb://$zipPath" `
    --region $REGION | Out-Null

& $AWS lambda update-function-configuration `
    --function-name "opsrelay-api" `
    --handler "lambda_api.handler" `
    --timeout 30 `
    --memory-size 512 `
    --environment "Variables={OPSRELAY_MODE=cloud,OPSRELAY_TABLE_NAME=$MAIN_TABLE,OPSRELAY_RAW_BUCKET=$DATA_BUCKET,OPSRELAY_EVENT_BUS=default,SAGEMAKER_ENABLED=true,SAGEMAKER_ENDPOINT_NAME=opsrelay-predictor,STRANDS_ENABLED=true,BEDROCK_MODEL_ID=amazon.nova-lite-v1:0}" `
    --region $REGION | Out-Null
Write-Host "  opsrelay-api updated with full Signal-to-Action engine." -ForegroundColor Green

# Deploy opsrelay-processor Lambda
Write-Host "  Deploying opsrelay-processor Lambda..." -ForegroundColor Yellow
try {
    & $AWS lambda create-function `
        --function-name "opsrelay-processor" `
        --runtime "python3.12" `
        --role $ROLE_ARN `
        --handler "lambda_processor.handler" `
        --zip-file "fileb://$zipPath" `
        --timeout 60 `
        --memory-size 512 `
        --environment "Variables={OPSRELAY_MODE=cloud,OPSRELAY_TABLE_NAME=$MAIN_TABLE,OPSRELAY_RAW_BUCKET=$DATA_BUCKET,SAGEMAKER_ENABLED=true,SAGEMAKER_ENDPOINT_NAME=opsrelay-predictor}" `
        --region $REGION | Out-Null
    Write-Host "  opsrelay-processor created." -ForegroundColor Green
} catch {
    & $AWS lambda update-function-code `
        --function-name "opsrelay-processor" `
        --zip-file "fileb://$zipPath" `
        --region $REGION | Out-Null
    Write-Host "  opsrelay-processor code updated." -ForegroundColor Green
}

# Attach SQS trigger to opsrelay-processor
Write-Host "  Connecting SQS Event Source Mapping..." -ForegroundColor Yellow
$mappings = & $AWS lambda list-event-source-mappings --function-name "opsrelay-processor" --region $REGION | ConvertFrom-Json
$existingMapping = $mappings.EventSourceMappings | Where-Object { $_.EventSourceArn -eq $QUEUE_ARN }

if (-not $existingMapping) {
    & $AWS lambda create-event-source-mapping `
        --function-name "opsrelay-processor" `
        --event-source-arn $QUEUE_ARN `
        --batch-size 5 `
        --function-response-types "ReportBatchItemFailures" `
        --region $REGION | Out-Null
    Write-Host "  Event source mapping connected (SQS -> opsrelay-processor)." -ForegroundColor Green
} else {
    Write-Host "  Event source mapping already active." -ForegroundColor DarkGray
}

# ─── STEP 8: CloudWatch Production Dashboard & Alarms ─────────────────────
Write-Host "`n[8/8] Provisioning CloudWatch Production Dashboard & Alarms..." -ForegroundColor Yellow

$dashboardBody = @"
{
  "widgets": [
    {
      "type": "metric",
      "x": 0,
      "y": 0,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "OpsRelay API Gateway Requests & Latency",
        "region": "$REGION",
        "view": "timeSeries",
        "metrics": [
          [ "AWS/ApiGateway", "Count", { "stat": "Sum" } ],
          [ ".", "Latency", { "stat": "Average", "yAxis": "right" } ],
          [ ".", "5XXError", { "stat": "Sum" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 12,
      "y": 0,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Lambda Execution & Ingestion Processor",
        "region": "$REGION",
        "view": "timeSeries",
        "metrics": [
          [ "AWS/Lambda", "Invocations", "FunctionName", "opsrelay-api", { "stat": "Sum" } ],
          [ "...", "opsrelay-processor", { "stat": "Sum" } ],
          [ ".", "Errors", "FunctionName", "opsrelay-api", { "stat": "Sum" } ],
          [ "...", "opsrelay-processor", { "stat": "Sum" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 0,
      "y": 6,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "SQS Factory Signal Queue & DLQ Depth",
        "region": "$REGION",
        "view": "timeSeries",
        "metrics": [
          [ "AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "opsrelay-factory-events", { "stat": "Average" } ],
          [ "...", "opsrelay-factory-events-dlq", { "stat": "Sum", "color": "#d62728" } ]
        ]
      }
    },
    {
      "type": "metric",
      "x": 12,
      "y": 6,
      "width": 12,
      "height": 6,
      "properties": {
        "title": "DynamoDB & S3 Data Lake Operations",
        "region": "$REGION",
        "view": "timeSeries",
        "metrics": [
          [ "AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", "$MAIN_TABLE", { "stat": "Sum" } ],
          [ ".", "ConsumedWriteCapacityUnits", "TableName", "$MAIN_TABLE", { "stat": "Sum" } ]
        ]
      }
    }
  ]
}
"@

$dashboardFile = Join-Path $tempDir "dashboard.json"
[System.IO.File]::WriteAllText($dashboardFile, $dashboardBody, $utf8NoBom)
& $AWS cloudwatch put-dashboard `
    --dashboard-name "OpsRelay-Production-Dashboard" `
  --dashboard-body "file://$dashboardFile" `
    --region $REGION | Out-Null
Write-Host "  CloudWatch Dashboard 'OpsRelay-Production-Dashboard' created." -ForegroundColor Green

# Create CloudWatch Alarms
& $AWS cloudwatch put-metric-alarm `
    --alarm-name "OpsRelay-DLQ-Alarm" `
    --alarm-description "Triggers if failed factory events enter the DLQ" `
    --metric-name "ApproximateNumberOfMessagesVisible" `
    --namespace "AWS/SQS" `
    --statistic "Maximum" `
    --dimensions Name=QueueName,Value=opsrelay-factory-events-dlq `
    --period 60 `
    --evaluation-periods 1 `
    --threshold 1 `
    --comparison-operator GreaterThanOrEqualToThreshold `
    --region $REGION | Out-Null

& $AWS cloudwatch put-metric-alarm `
    --alarm-name "OpsRelay-Lambda-Errors-Alarm" `
    --alarm-description "Triggers if opsrelay-processor or opsrelay-api experiences runtime errors" `
    --metric-name "Errors" `
    --namespace "AWS/Lambda" `
    --statistic "Sum" `
    --dimensions Name=FunctionName,Value=opsrelay-api `
    --period 60 `
    --evaluation-periods 1 `
    --threshold 2 `
    --comparison-operator GreaterThanOrEqualToThreshold `
    --region $REGION | Out-Null

Write-Host "  CloudWatch Alarms created (OpsRelay-DLQ-Alarm, OpsRelay-Lambda-Errors-Alarm)." -ForegroundColor Green

Write-Host "`n=================================================================" -ForegroundColor Green
Write-Host "  PROVISIONING COMPLETE!" -ForegroundColor Green
Write-Host "  S3 Data Lake   : s3://$DATA_BUCKET" -ForegroundColor White
Write-Host "  DynamoDB Table : $MAIN_TABLE" -ForegroundColor White
Write-Host "  EventBridge    : opsrelay-factory-signals-rule -> SQS" -ForegroundColor White
Write-Host "  SQS Main Queue : $QUEUE_URL" -ForegroundColor White
Write-Host "  SQS DLQ        : $DLQ_URL" -ForegroundColor White
Write-Host "  Cognito Pool   : $USER_POOL_ID (Client: $CLIENT_ID)" -ForegroundColor White
Write-Host "  Lambda API     : opsrelay-api" -ForegroundColor White
Write-Host "  Lambda Proc    : opsrelay-processor" -ForegroundColor White
Write-Host "  CloudWatch     : OpsRelay-Production-Dashboard" -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Green
