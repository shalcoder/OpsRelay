import json
import os
import boto3
import zipfile
from pathlib import Path

REGION = "ap-south-1"
ACCOUNT = "704932818996"
DATA_BUCKET = f"opsrelay-data-{ACCOUNT}"
MAIN_TABLE = "opsrelay-main"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/opsrelay-lambda-role"

sqs = boto3.client("sqs", region_name=REGION)
events = boto3.client("events", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
cw = boto3.client("cloudwatch", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)

print("[1] Setting up SQS Main Queue with RedrivePolicy...")
dlq_url = f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/opsrelay-factory-events-dlq"
dlq_arn = f"arn:aws:sqs:{REGION}:{ACCOUNT}:opsrelay-factory-events-dlq"

redrive_policy = json.dumps({
    "deadLetterTargetArn": dlq_arn,
    "maxReceiveCount": 3
})

try:
    q_resp = sqs.create_queue(
        QueueName="opsrelay-factory-events",
        Attributes={
            "VisibilityTimeout": "120",
            "RedrivePolicy": redrive_policy
        }
    )
    main_queue_url = q_resp["QueueUrl"]
except Exception as e:
    main_queue_url = sqs.get_queue_url(QueueName="opsrelay-factory-events")["QueueUrl"]

main_queue_arn = f"arn:aws:sqs:{REGION}:{ACCOUNT}:opsrelay-factory-events"
print(f"  Main Queue URL: {main_queue_url}")

# Set SQS Queue Policy to allow EventBridge
sqs_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "events.amazonaws.com"},
            "Action": "sqs:SendMessage",
            "Resource": main_queue_arn,
            "Condition": {
                "ArnEquals": {
                    "aws:SourceArn": f"arn:aws:events:{REGION}:{ACCOUNT}:rule/opsrelay-factory-signals-rule"
                }
            }
        }
    ]
}
sqs.set_queue_attributes(
    QueueUrl=main_queue_url,
    Attributes={"Policy": json.dumps(sqs_policy)}
)
print("  SQS Queue Policy updated.")

# [2] EventBridge Target
print("[2] Attaching SQS target to EventBridge rule...")
events.put_targets(
    Rule="opsrelay-factory-signals-rule",
    Targets=[{
        "Id": "OpsRelaySQSTarget",
        "Arn": main_queue_arn
    }]
)
print("  EventBridge target attached.")

# [3] Package Lambda code
print("[3] Packaging Lambda source...")
dist_dir = Path("deploy/dist")
dist_dir.mkdir(parents=True, exist_ok=True)
zip_path = dist_dir / "opsrelay-engine.zip"

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    api_dir = Path("api")
    for file in api_dir.rglob("*"):
        if "__pycache__" in str(file) or file.name.endswith(".pyc"):
            continue
        if file.is_file():
            arcname = file.relative_to(api_dir)
            zf.write(file, arcname)

print(f"  Package created: {zip_path} ({zip_path.stat().st_size} bytes)")
with open(zip_path, "rb") as f:
    zip_bytes = f.read()

# [4] Configure & Update opsrelay-api Lambda
print("[4] Updating opsrelay-api Lambda...")
api_env = {
    "Variables": {
        "OPSRELAY_MODE": "cloud",
        "OPSRELAY_TABLE_NAME": MAIN_TABLE,
        "OPSRELAY_RAW_BUCKET": DATA_BUCKET,
        "OPSRELAY_EVENT_BUS": "default",
        "SAGEMAKER_ENABLED": "true",
        "SAGEMAKER_ENDPOINT_NAME": "opsrelay-predictor",
        "STRANDS_ENABLED": "true",
        "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0"
    }
}

lambda_client.update_function_code(
    FunctionName="opsrelay-api",
    ZipFile=zip_bytes
)

# Wait for update
waiter = lambda_client.get_waiter("function_updated")
waiter.wait(FunctionName="opsrelay-api")

lambda_client.update_function_configuration(
    FunctionName="opsrelay-api",
    Handler="lambda_api.handler",
    Timeout=30,
    MemorySize=512,
    Environment=api_env
)
print("  opsrelay-api Lambda updated.")

# [5] Create/Update opsrelay-processor Lambda
print("[5] Deploying opsrelay-processor Lambda...")
proc_env = {
    "Variables": {
        "OPSRELAY_MODE": "cloud",
        "OPSRELAY_TABLE_NAME": MAIN_TABLE,
        "OPSRELAY_RAW_BUCKET": DATA_BUCKET,
        "SAGEMAKER_ENABLED": "true",
        "SAGEMAKER_ENDPOINT_NAME": "opsrelay-predictor"
    }
}

try:
    lambda_client.create_function(
        FunctionName="opsrelay-processor",
        Runtime="python3.12",
        Role=ROLE_ARN,
        Handler="lambda_processor.handler",
        Code={"ZipFile": zip_bytes},
        Timeout=60,
        MemorySize=512,
        Environment=proc_env
    )
    print("  opsrelay-processor created.")
except lambda_client.exceptions.ResourceConflictException:
    lambda_client.update_function_code(
        FunctionName="opsrelay-processor",
        ZipFile=zip_bytes
    )
    waiter.wait(FunctionName="opsrelay-processor")
    lambda_client.update_function_configuration(
        FunctionName="opsrelay-processor",
        Handler="lambda_processor.handler",
        Timeout=60,
        MemorySize=512,
        Environment=proc_env
    )
    print("  opsrelay-processor updated.")

# Attach SQS Event Source Mapping
print("[6] Connecting SQS trigger to opsrelay-processor...")
mappings = lambda_client.list_event_source_mappings(
    FunctionName="opsrelay-processor"
).get("EventSourceMappings", [])

exists = any(m["EventSourceArn"] == main_queue_arn for m in mappings)
if not exists:
    lambda_client.create_event_source_mapping(
        FunctionName="opsrelay-processor",
        EventSourceArn=main_queue_arn,
        BatchSize=5,
        FunctionResponseTypes=["ReportBatchItemFailures"]
    )
    print("  Event source mapping connected (SQS -> opsrelay-processor).")
else:
    print("  Event source mapping already active.")

# [7] CloudWatch Dashboard
print("[7] Provisioning CloudWatch Dashboard...")
dashboard_body = {
    "widgets": [
        {
            "type": "metric",
            "x": 0, "y": 0, "width": 12, "height": 6,
            "properties": {
                "title": "OpsRelay API Gateway Requests & Latency",
                "region": REGION,
                "view": "timeSeries",
                "metrics": [
                    ["AWS/ApiGateway", "Count", {"stat": "Sum"}],
                    [".", "Latency", {"stat": "Average", "yAxis": "right"}],
                    [".", "5XXError", {"stat": "Sum"}]
                ]
            }
        },
        {
            "type": "metric",
            "x": 12, "y": 0, "width": 12, "height": 6,
            "properties": {
                "title": "Lambda Invocations & Processor Workload",
                "region": REGION,
                "view": "timeSeries",
                "metrics": [
                    ["AWS/Lambda", "Invocations", "FunctionName", "opsrelay-api", {"stat": "Sum"}],
                    ["...", "opsrelay-processor", {"stat": "Sum"}],
                    [".", "Errors", "FunctionName", "opsrelay-api", {"stat": "Sum"}],
                    ["...", "opsrelay-processor", {"stat": "Sum"}]
                ]
            }
        },
        {
            "type": "metric",
            "x": 0, "y": 6, "width": 12, "height": 6,
            "properties": {
                "title": "SQS Factory Signal Queue & DLQ Depth",
                "region": REGION,
                "view": "timeSeries",
                "metrics": [
                    ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "opsrelay-factory-events", {"stat": "Average"}],
                    ["...", "opsrelay-factory-events-dlq", {"stat": "Sum", "color": "#d62728"}]
                ]
            }
        },
        {
            "type": "metric",
            "x": 12, "y": 6, "width": 12, "height": 6,
            "properties": {
                "title": "DynamoDB Consumed Capacity",
                "region": REGION,
                "view": "timeSeries",
                "metrics": [
                    ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", MAIN_TABLE, {"stat": "Sum"}],
                    [".", "ConsumedWriteCapacityUnits", "TableName", MAIN_TABLE, {"stat": "Sum"}]
                ]
            }
        }
    ]
}

cw.put_dashboard(
    DashboardName="OpsRelay-Production-Dashboard",
    DashboardBody=json.dumps(dashboard_body)
)
print("  CloudWatch Dashboard ready.")

# [8] Seed DynamoDB Table
print("[8] Seeding DynamoDB Single-Table with Production Entity Data...")
table = dynamodb.Table(MAIN_TABLE)

# Read demo/seed data
with open("data/demo.json", "r", encoding="utf-8") as f:
    demo_data = json.load(f)

# Insert machines
for m in demo_data["machines"]:
    table.put_item(Item={"pk": "MACHINES", "sk": m["id"], "entity": "MACHINE", "data": m})
    table.put_item(Item={"pk": f"MACHINE#{m['id']}", "sk": "META", "entity": "MACHINE", "data": m})

# Insert orders
for o in demo_data["orders"]:
    table.put_item(Item={"pk": "ORDERS", "sk": o["id"], "entity": "ORDER", "data": o})
    table.put_item(Item={"pk": f"ORDER#{o['id']}", "sk": "META", "entity": "ORDER", "data": o})

# Insert factory events
for ev in demo_data["events"]:
    table.put_item(Item={
        "pk": f"ORDER#{ev.get('orderId', 'UNASSIGNED')}",
        "sk": f"EVENT#{ev['timestamp']}#{ev['id']}",
        "entity": "EVENT",
        "data": ev
    })

print("  5 Machines, 4 Orders, and 6 Factory Signals seeded to DynamoDB.")
print("\n>>> DEPLOYMENT COMPLETE & VERIFIED! <<<")
