"""
OpsRelay Lambda Handler Tests
Uses moto to mock DynamoDB locally — no real AWS calls.
"""
import json
import os
import pytest
import boto3
from moto import mock_aws

# ── Set environment variables before importing handler ────────────
os.environ.setdefault("AWS_DEFAULT_REGION",    "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID",     "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN",    "testing")
os.environ.setdefault("AWS_SESSION_TOKEN",     "testing")
os.environ.setdefault("MACHINES_TABLE",        "opsrelay-machines")
os.environ.setdefault("ORDERS_TABLE",          "opsrelay-orders")
os.environ.setdefault("RECOMMENDATIONS_TABLE", "opsrelay-recommendations")
os.environ.setdefault("ALERTS_TABLE",          "opsrelay-alerts")
os.environ.setdefault("TELEMETRY_TABLE",       "opsrelay-telemetry")


# ── Fixtures ──────────────────────────────────────────────────────
@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"]     = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"]    = "testing"
    os.environ["AWS_SESSION_TOKEN"]     = "testing"
    os.environ["AWS_DEFAULT_REGION"]    = "ap-south-1"


@pytest.fixture
def dynamodb_tables(aws_credentials):
    """Create all required DynamoDB tables with moto."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-south-1")

        tables = [
            ("opsrelay-machines",        "machine_id"),
            ("opsrelay-orders",          "order_id"),
            ("opsrelay-recommendations", "rec_id"),
            ("opsrelay-alerts",          "alert_id"),
            ("opsrelay-telemetry",       "machine_id"),
        ]
        for table_name, key in tables:
            client.create_table(
                TableName=table_name,
                AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
                KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
                BillingMode="PAY_PER_REQUEST",
            )

        # Seed sample data
        dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
        machines_table = dynamodb.Table("opsrelay-machines")
        machines_table.put_item(Item={
            "machine_id": "M-001",
            "name": "Packaging Line A1",
            "status": "RUNNING",
            "health_score": 98,
            "location": "Plant 1",
            "model": "PK-5000",
        })
        machines_table.put_item(Item={
            "machine_id": "M-002",
            "name": "Conveyor Belt B3",
            "status": "WARNING",
            "health_score": 72,
            "location": "Plant 1",
            "model": "CB-3000",
        })

        orders_table = dynamodb.Table("opsrelay-orders")
        orders_table.put_item(Item={
            "order_id": "ORD-00125",
            "customer": "Tech Solutions",
            "status": "DELAYED",
            "destination": "Chicago, IL",
            "risk_score": 72,
        })

        yield


def make_event(method, path, body=None):
    """Helper to create API Gateway proxy event."""
    return {
        "httpMethod": method,
        "path": path,
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": None,
        "pathParameters": None,
        "body": json.dumps(body) if body else None,
        "isBase64Encoded": False,
    }


# ── Tests ─────────────────────────────────────────────────────────
class TestDashboardEndpoint:
    @mock_aws
    def test_dashboard_returns_200(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/dashboard")
        response = handler(event, {})
        assert response["statusCode"] == 200

    @mock_aws
    def test_dashboard_has_machines_and_orders(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/dashboard")
        response = handler(event, {})
        body = json.loads(response["body"])
        assert "machines" in body
        assert "orders" in body
        assert "kpis" in body

    @mock_aws
    def test_dashboard_kpis_structure(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/dashboard")
        response = handler(event, {})
        kpis = json.loads(response["body"])["kpis"]
        required_keys = ["total_machines", "active_alerts", "orders_in_transit", "on_time_delivery"]
        for key in required_keys:
            assert key in kpis, f"Missing KPI: {key}"


class TestMachinesEndpoint:
    @mock_aws
    def test_list_machines(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/machines")
        response = handler(event, {})
        assert response["statusCode"] == 200
        machines = json.loads(response["body"])
        assert isinstance(machines, list)
        assert len(machines) >= 1

    @mock_aws
    def test_get_single_machine(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/machines/M-001")
        response = handler(event, {})
        assert response["statusCode"] == 200
        machine = json.loads(response["body"])
        assert machine["machine_id"] == "M-001"
        assert machine["name"] == "Packaging Line A1"

    @mock_aws
    def test_machine_not_found(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/machines/NONEXISTENT")
        response = handler(event, {})
        assert response["statusCode"] == 404

    @mock_aws
    def test_create_machine(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        new_machine = {
            "machine_id": "M-TEST",
            "name": "Test Machine",
            "status": "RUNNING",
            "health_score": 99,
            "location": "Test Plant",
            "model": "TM-1000",
        }
        event = make_event("POST", "/api/machines", new_machine)
        response = handler(event, {})
        assert response["statusCode"] == 201


class TestOrdersEndpoint:
    @mock_aws
    def test_list_orders(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/orders")
        response = handler(event, {})
        assert response["statusCode"] == 200
        orders = json.loads(response["body"])
        assert isinstance(orders, list)

    @mock_aws
    def test_get_single_order(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/orders/ORD-00125")
        response = handler(event, {})
        assert response["statusCode"] == 200
        order = json.loads(response["body"])
        assert order["order_id"] == "ORD-00125"


class TestCorsHeaders:
    @mock_aws
    def test_options_preflight(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("OPTIONS", "/api/dashboard")
        response = handler(event, {})
        assert response["statusCode"] == 200
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"

    @mock_aws
    def test_cors_headers_present(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/machines")
        response = handler(event, {})
        assert "Access-Control-Allow-Origin" in response["headers"]


class TestUnknownRoutes:
    @mock_aws
    def test_unknown_route_returns_404(self, dynamodb_tables):
        from deploy.lambda.lambda_function import handler
        event = make_event("GET", "/api/nonexistent")
        response = handler(event, {})
        assert response["statusCode"] == 404
