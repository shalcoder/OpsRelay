from __future__ import annotations

import json
import os
from typing import Any

from core.service import OpsRelayService

service = OpsRelayService()


def _response(status: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.getenv("CORS_ORIGINS", "*").split(",")[0],
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }


def _body(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("body")
    if not value: return {}
    if isinstance(value, dict): return value
    try: return json.loads(value)
    except Exception: return {}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "GET")
    if method == "OPTIONS": return _response(204, {})
    path = event.get("rawPath") or event.get("path") or "/"
    if path.startswith("/prod"):
        path = path[5:] or "/"
    if path.startswith("/api"):
        path = path[4:] or "/"
    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/") or "/"
    try:
        if method == "GET" and path in ("/health", "/"): return _response(200, {"status":"ok", "mode":service.mode, "timestamp":service.dashboard()["plant"]})
        if method == "GET" and path == "/dashboard": return _response(200, service.dashboard())
        if method == "GET" and path == "/orders": return _response(200, service.store.list_orders())
        if method == "POST" and path == "/orders": return _response(201, service.create_order(_body(event)))
        if method == "POST" and path.startswith("/orders/") and path.endswith("/reschedule"):
            parts = path.split("/")
            order_id = parts[2]
            data = _body(event)
            return _response(200, service.reschedule_order(order_id, data.get("newDueDate") or data.get("dueDate"), data.get("newBatchSize") or data.get("quantity"), data.get("actor", "SUPERVISOR-DIR-01")))
        if method == "GET" and path.startswith("/orders/"):
            order_id = path.split("/", 2)[2]
            order = service.get_order(order_id)
            if not order: return _response(404, {"error":"Order not found"})
            return _response(200, {"order":order, "risk":service.get_risk(order_id), "events":service.store.list_events(order_id, 50), "recommendations":service.store.list_recommendations(order_id), "actions":service.store.list_actions(order_id)})
        if method == "GET" and path == "/machines": return _response(200, service.store.list_machines())
        if method == "POST" and path == "/machines": return _response(201, service.create_machine(_body(event)))
        if method == "POST" and path.startswith("/machines/") and path.endswith("/transition"):
            parts = path.split("/")
            machine_id = parts[2]
            data = _body(event)
            return _response(200, service.transition_machine(machine_id, data.get("action", "DIAGNOSE"), data.get("actor", "MAINTENANCE-LEAD")))
        if method == "GET" and path.startswith("/risk/"):
            return _response(200, service.get_risk(path.split("/",2)[2]))
        if method == "GET" and path == "/events": return _response(200, service.store.list_events(limit=100))
        if method == "POST" and path == "/events": return _response(201, service.ingest_event(_body(event)))
        if method == "POST" and path == "/risk/recalculate":
            order_id = _body(event).get("orderId")
            return _response(200, service.calculate_risk(order_id))
        if method == "POST" and path == "/agent/query":
            data = _body(event)
            return _response(200, service.ask_agent(data.get("question", ""), data.get("orderId")))
        if method == "GET" and path == "/agent/sessions":
            return _response(200, service.store.list_agent_sessions())
        if method == "GET" and path == "/recommendations": return _response(200, service.store.list_recommendations())
        if method == "POST" and path == "/actions":
            data = _body(event)
            return _response(201, service.create_action(data["recommendationId"], data.get("approvedBy", "SUP-001")))
        if method == "GET" and path == "/actions": return _response(200, service.store.list_actions())
        if method == "GET" and path == "/audit": return _response(200, service.store.list_audit())
        return _response(404, {"error":"Route not found", "path":path})
    except KeyError as exc:
        return _response(404, {"error":f"Unknown resource: {exc.args[0]}"})
    except Exception as exc:
        return _response(500, {"error":str(exc)})
