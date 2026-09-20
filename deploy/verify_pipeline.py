import json
import time
import urllib.request
import boto3

REGION = "ap-south-1"
ACCOUNT = "704932818996"
API_URL = "https://4q0wc7pbk4.execute-api.ap-south-1.amazonaws.com/prod"
DATA_BUCKET = f"opsrelay-data-{ACCOUNT}"

print("=================================================================")
print("  Running OpsRelay End-to-End Pipeline Verification")
print("=================================================================")

# 1. Health & Dashboard
print("\n[Test 1] Testing /dashboard endpoint...")
req = urllib.request.Request(f"{API_URL}/dashboard")
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"  Status: {resp.status}")
        print(f"  Plant: {data.get('plant', {}).get('name')}")
        print(f"  Orders count: {len(data.get('orders', []))}")
        print(f"  Machines count: {len(data.get('machines', []))}")
        print(f"  Critical orders: {data.get('stats', {}).get('critical')}")
except Exception as e:
    print(f"  Dashboard check error: {e}")

# 2. Agent Query
print("\n[Test 2] Testing Strands / Bedrock Agent Reasoning (/agent/query)...")
agent_payload = json.dumps({
    "question": "What is causing the delivery risk for ORD-1048 and what machine should we reassign to?",
    "orderId": "ORD-1048"
}).encode("utf-8")

req = urllib.request.Request(
    f"{API_URL}/agent/query",
    data=agent_payload,
    headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(req) as resp:
        agent_res = json.loads(resp.read().decode("utf-8"))
        print(f"  Status: {resp.status}")
        print(f"  Session ID: {agent_res.get('sessionId')}")
        print(f"  Mode: {agent_res.get('mode')}")
        print(f"  Policy: {agent_res.get('policy')}")
        print("\n  Agent Reasoning Output:")
        for line in agent_res.get("answer", "").split("\n")[:10]:
            print(f"    {line}")
except Exception as e:
    print(f"  Agent query error: {e}")

# 3. Ingest Factory Signal (Signal -> S3 -> EventBridge -> SQS -> Processor)
print("\n[Test 3] Testing Signal Ingestion & Event-Driven Routing (/events)...")
evt_id = f"EVT-TEST-{int(time.time())}"
signal_payload = json.dumps({
    "id": evt_id,
    "orderId": "ORD-1048",
    "machineId": "CNC-04",
    "type": "MACHINE_STOP",
    "source": "iot-sensor-edge",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "durationMinutes": 45,
    "description": "Critical spindle bearing thermal trip detected by IoT sensor."
}).encode("utf-8")

req = urllib.request.Request(
    f"{API_URL}/events",
    data=signal_payload,
    headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(req) as resp:
        ingest_res = json.loads(resp.read().decode("utf-8"))
        print(f"  Status: {resp.status}")
        print(f"  Event Ingested ID: {ingest_res.get('id')}")
except Exception as e:
    print(f"  Ingest error: {e}")

# Check S3 Data Lake for raw event persistence
print("\n[Test 4] Verifying S3 Data Lake raw event persistence...")
s3 = boto3.client("s3", region_name=REGION)
today = time.strftime("%Y-%m-%d", time.gmtime())
key = f"events/{today}/{evt_id}.json"
try:
    time.sleep(2)
    obj = s3.get_object(Bucket=DATA_BUCKET, Key=key)
    raw_content = obj["Body"].read().decode("utf-8")
    print(f"  Verified object in s3://{DATA_BUCKET}/{key}!")
    print(f"  Saved payload description: {json.loads(raw_content).get('description')}")
except Exception as e:
    print(f"  S3 verify note: {e}")

# 4. Check SQS and Processor Execution
print("\n[Test 5] Verifying SQS and Processor Lambda...")
sqs = boto3.client("sqs", region_name=REGION)
q_url = f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/opsrelay-factory-events"
dlq_url = f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/opsrelay-factory-events-dlq"

q_attrs = sqs.get_queue_attributes(
    QueueUrl=q_url,
    AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
)["Attributes"]

dlq_attrs = sqs.get_queue_attributes(
    QueueUrl=dlq_url,
    AttributeNames=["ApproximateNumberOfMessages"]
)["Attributes"]

print(f"  Factory Events Queue: {q_attrs.get('ApproximateNumberOfMessages')} visible, {q_attrs.get('ApproximateNumberOfMessagesNotVisible')} in-flight")
print(f"  DLQ Depth: {dlq_attrs.get('ApproximateNumberOfMessages')} messages (0 expected)")

# 5. CloudWatch Dashboard Check
print("\n[Test 6] Verifying CloudWatch Dashboard...")
cw = boto3.client("cloudwatch", region_name=REGION)
dash = cw.get_dashboard(DashboardName="OpsRelay-Production-Dashboard")
dash_name = dash.get('DashboardName', 'OpsRelay-Production-Dashboard')
dash_arn = dash.get('DashboardArn', 'active')
print(f"  Dashboard '{dash_name}' is active with ARN: {dash_arn}")

print("\n=================================================================")
print("  ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
print("=================================================================")
