import json
import boto3
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
    print(f"REQUEST: {method} {path}")

    if method == "OPTIONS":
        return cors_response(200, {})

    try:
        # ─── Dashboard ─────────────────────────────────────────────
        if path in ("/api/dashboard", "/api/dashboard/"):
            machines = dynamodb.Table("opsrelay-machines").scan().get("Items", [])
            orders   = dynamodb.Table("opsrelay-orders").scan().get("Items", [])
            alerts   = dynamodb.Table("opsrelay-alerts").scan().get("Items", [])
            recs     = dynamodb.Table("opsrelay-recommendations").scan().get("Items", [])

            healthy  = sum(1 for m in machines if m.get("status") == "RUNNING")
            warning  = sum(1 for m in machines if m.get("status") == "WARNING")
            critical = sum(1 for m in machines if m.get("status") == "CRITICAL")

            machine_trend = [
                {"date": "1/10", "healthy": 60, "warning": 35, "critical": 5},
                {"date": "1/13", "healthy": 65, "warning": 30, "critical": 5},
                {"date": "1/16", "healthy": 70, "warning": 25, "critical": 5},
                {"date": "1/19", "healthy": 75, "warning": 20, "critical": 5},
                {"date": "1/22", "healthy": 80, "warning": 15, "critical": 5},
                {"date": "1/25", "healthy": healthy, "warning": warning, "critical": critical},
            ]

            return cors_response(200, {
                "machines": machines,
                "orders":   orders,
                "alerts":   alerts,
                "recommendations": recs,
                "machine_trend": machine_trend,
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

        # ─── Machines ──────────────────────────────────────────────
        elif path.startswith("/api/machines"):
            table = dynamodb.Table("opsrelay-machines")
            parts = [p for p in path.strip("/").split("/") if p]

            if method == "GET":
                if len(parts) >= 3 and parts[2]:
                    result = table.get_item(Key={"machine_id": parts[2]})
                    item = result.get("Item")
                    if item:
                        return cors_response(200, item)
                    return cors_response(404, {"error": "Machine not found"})
                return cors_response(200, table.scan().get("Items", []))

            elif method in ("PUT", "PATCH"):
                body = json.loads(event.get("body", "{}"))
                parts = [p for p in path.strip("/").split("/") if p]
                if len(parts) >= 3:
                    table.update_item(
                        Key={"machine_id": parts[2]},
                        UpdateExpression="SET #s = :s",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={":s": body.get("status", "RUNNING")}
                    )
                return cors_response(200, {"message": "Updated"})

            elif method == "POST":
                body = json.loads(event.get("body", "{}"))
                table.put_item(Item=body)
                return cors_response(201, body)

        # ─── Orders ────────────────────────────────────────────────
        elif path.startswith("/api/orders"):
            table = dynamodb.Table("opsrelay-orders")
            parts = [p for p in path.strip("/").split("/") if p]

            if method == "GET":
                if len(parts) >= 3 and parts[2]:
                    result = table.get_item(Key={"order_id": parts[2]})
                    item = result.get("Item")
                    if item:
                        return cors_response(200, item)
                    return cors_response(404, {"error": "Order not found"})
                return cors_response(200, table.scan().get("Items", []))

            elif method == "POST":
                body = json.loads(event.get("body", "{}"))
                table.put_item(Item=body)
                return cors_response(201, body)

            elif method in ("PUT", "PATCH"):
                body = json.loads(event.get("body", "{}"))
                parts = [p for p in path.strip("/").split("/") if p]
                if len(parts) >= 3:
                    table.update_item(
                        Key={"order_id": parts[2]},
                        UpdateExpression="SET #s = :s",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={":s": body.get("status", "IN_TRANSIT")}
                    )
                return cors_response(200, {"message": "Updated"})

        # ─── Recommendations / Approvals ───────────────────────────
        elif path.startswith("/api/recommendations"):
            table = dynamodb.Table("opsrelay-recommendations")
            if method == "GET":
                return cors_response(200, table.scan().get("Items", []))
            elif method == "POST":
                body = json.loads(event.get("body", "{}"))
                table.put_item(Item=body)
                return cors_response(201, body)

        elif path.startswith("/api/approvals"):
            table = dynamodb.Table("opsrelay-recommendations")
            if method == "GET":
                items = table.scan().get("Items", [])
                pending = [i for i in items if i.get("status") == "PENDING"]
                return cors_response(200, pending)
            elif method in ("PUT", "PATCH"):
                body = json.loads(event.get("body", "{}"))
                parts = [p for p in path.strip("/").split("/") if p]
                if len(parts) >= 3:
                    table.update_item(
                        Key={"rec_id": parts[2]},
                        UpdateExpression="SET #s = :s",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={":s": body.get("status", "APPROVED")}
                    )
                return cors_response(200, {"message": "Updated"})

        # ─── Alerts ────────────────────────────────────────────────
        elif path.startswith("/api/alerts"):
            table = dynamodb.Table("opsrelay-alerts")
            if method == "GET":
                return cors_response(200, table.scan().get("Items", []))
            elif method == "POST":
                body = json.loads(event.get("body", "{}"))
                table.put_item(Item=body)
                return cors_response(201, body)

        # ─── Telemetry ─────────────────────────────────────────────
        elif path.startswith("/api/telemetry"):
            table = dynamodb.Table("opsrelay-telemetry")
            if method == "POST":
                body = json.loads(event.get("body", "{}"))
                table.put_item(Item=body)
                return cors_response(201, {"message": "Telemetry recorded"})
            return cors_response(200, table.scan().get("Items", []))

        return cors_response(404, {"error": f"Route not found: {method} {path}"})

    except Exception as e:
        print(f"HANDLER ERROR: {e}")
        return cors_response(500, {"error": str(e)})
