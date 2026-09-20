from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    import boto3
except Exception:  # pragma: no cover
    boto3 = None

from .agent import OpsRelayAgent
from .predictor import SageMakerPredictor
from .risk import assess_order
from .store import BaseStore, make_store


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpsRelayService:
    def __init__(self, store: BaseStore | None = None) -> None:
        self.store = store or make_store()
        self.predictor = SageMakerPredictor()
        self.agent = OpsRelayAgent(self)
        self.mode = os.getenv("OPSRELAY_MODE", "local").lower()
        self.region = os.getenv("AWS_REGION", "ap-south-1")
        self.event_bus = os.getenv("OPSRELAY_EVENT_BUS", "default")
        self.raw_bucket = os.getenv("OPSRELAY_RAW_BUCKET", "")
        self.events_client = boto3.client("events", region_name=self.region) if boto3 and self.mode == "cloud" else None
        self.s3_client = boto3.client("s3", region_name=self.region) if boto3 and self.mode == "cloud" else None

    def dashboard(self) -> dict[str, Any]:
        orders = self.store.list_orders()
        raw_machines = self.store.list_machines()
        # Map active order to assigned machine dynamically
        active_order_by_machine = {o["assignedMachineId"]: o["id"] for o in orders if o.get("assignedMachineId") and o.get("status") in {"IN_PROGRESS", "RUNNING"}}
        machines = []
        for m in raw_machines:
            m_copy = dict(m)
            assigned_job = active_order_by_machine.get(m["id"])
            if assigned_job:
                m_copy["currentOrderId"] = assigned_job
                if m_copy.get("status") == "AVAILABLE":
                    m_copy["status"] = "RUNNING"
            else:
                m_copy["currentOrderId"] = None
                if m_copy.get("status") == "RUNNING":
                    m_copy["status"] = "AVAILABLE"
            machines.append(m_copy)
        risks = [self.get_or_calculate_risk(o["id"]) for o in orders]
        by_severity = {k: sum(1 for r in risks if r["severity"] == k) for k in ["CRITICAL", "HIGH", "WATCH", "HEALTHY"]}
        return {
            "plant": {"id": "PLANT-001", "name": "Apex Precision Works", "location": "Coimbatore, India"},
            "stats": {
                "orders": len(orders),
                "atRisk": sum(1 for r in risks if r["riskScore"] >= 60),
                "critical": by_severity["CRITICAL"],
                "machinesDown": sum(1 for m in machines if m["status"] == "STOPPED"),
                "recoveryActions": len(self.store.list_actions()),
            },
            "orders": sorted([dict(o, risk=self.get_or_calculate_risk(o["id"])) for o in orders], key=lambda x: x["risk"]["riskScore"], reverse=True),
            "machines": machines,
            "recentEvents": self.store.list_events(limit=12),
            "recentActions": self.store.list_actions()[:8],
            "recommendations": self.store.list_recommendations(),
        }

    def build_dashboard_context(self) -> dict[str, Any]:
        d = self.dashboard()
        return {"orders": d["orders"][:6], "machines": d["machines"], "recentEvents": d["recentEvents"][:8]}

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        return self.store.get_order(order_id)

    def build_features(self, order_id: str) -> dict[str, Any]:
        order = self.store.get_order(order_id)
        if not order: raise KeyError(order_id)
        events = self.store.list_events(order_id, 100)
        machines = self.store.list_machines()
        due = datetime.fromisoformat(order["dueDate"].replace("Z", "+00:00"))
        due_hours = (due - datetime.now(timezone.utc)).total_seconds()/3600
        qty = max(1, int(order.get("quantity", 1)))
        rework = sum(int(e.get("reworkUnits", 0)) for e in events if e.get("type") == "QUALITY_REWORK")
        downtime = sum(float(e.get("durationMinutes", 0)) for e in events if e.get("type") in {"MACHINE_STOP", "MACHINE_DEGRADED"})
        material = max([float(e.get("delayHours", 0)) for e in events if e.get("type") == "MATERIAL_DELAY"] or [0])
        machine = next((m for m in machines if m["id"] == order.get("assignedMachineId")), {})
        return {
            "downtimeMinutes": downtime,
            "reworkRate": rework/qty,
            "materialDelayHours": material,
            "remainingRatio": max(0, 1 - int(order.get("completedQuantity", 0))/qty),
            "dueHours": due_hours,
            "machineStatus": machine.get("status", "AVAILABLE"),
            "machineId": machine.get("id"),
            "productionRate": float(machine.get("capacityPerHour", 20)),
        }

    def calculate_risk(self, order_id: str) -> dict[str, Any]:
        order = self.store.get_order(order_id)
        if not order: raise KeyError(order_id)
        features = self.build_features(order_id)
        prediction = self.predictor.predict(features)
        risk = assess_order(order, self.store.list_machines(), self.store.list_events(order_id, 100), prediction)
        self.store.put_risk(risk)

        # Diagram 07: UML State Machine (Production Order) Transitions
        qty = int(order.get("quantity", 1))
        comp = int(order.get("completedQuantity", 0))
        current_status = order.get("status", "IN_PROGRESS")
        new_status = current_status

        if comp >= qty:
            new_status = "COMPLETED"
        else:
            try:
                due = datetime.fromisoformat(order["dueDate"].replace("Z", "+00:00"))
                is_overdue = datetime.now(timezone.utc) > due
            except Exception:
                is_overdue = False

            if is_overdue:
                new_status = "DELAYED"
            elif risk["riskScore"] >= 60:
                if current_status in {"CREATED", "IN_PROGRESS"}:
                    new_status = "AT_RISK"
            elif risk["riskScore"] < 50:
                if current_status in {"AT_RISK", "RECOVERY_VERIFIED", "DELAYED"}:
                    new_status = "IN_PROGRESS"

        if new_status != current_status:
            self.store.update_order(order_id, {"status": new_status})
            order["status"] = new_status

        self._generate_recommendation(order, risk)
        return risk

    def get_or_calculate_risk(self, order_id: str) -> dict[str, Any]:
        return self.store.get_risk(order_id) or self.calculate_risk(order_id)

    def get_risk(self, order_id: str) -> dict[str, Any]:
        return self.get_or_calculate_risk(order_id)

    def available_machines(self, order_id: str) -> list[dict[str, Any]]:
        order = self.store.get_order(order_id)
        if not order: return []
        assigned = order.get("assignedMachineId")
        return [m for m in self.store.list_machines() if m["id"] != assigned and m.get("status") == "AVAILABLE" and m.get("capabilities", []) and order.get("process") in m.get("capabilities", [])]

    def build_context(self, order_id: str) -> dict[str, Any]:
        order = self.store.get_order(order_id)
        if not order: return {"order": None}
        return {
            "order": order,
            "risk": self.get_or_calculate_risk(order_id),
            "availableMachines": self.available_machines(order_id),
            "allMachines": self.store.list_machines(),
            "events": self.store.list_events(order_id, 20),
            "actions": self.store.list_actions(order_id),
        }

    def create_order(self, data: dict[str, Any]) -> dict[str, Any]:
        order_id = data.get("id") or f"ORD-{uuid.uuid4().hex[:4].upper()}"
        order = {
            "id": order_id,
            "customer": data.get("customer", "Apex Customer"),
            "product": data.get("product", "Machined Component"),
            "process": data.get("process", "MACHINING"),
            "quantity": max(1, int(data.get("quantity", 500))),
            "completedQuantity": max(0, int(data.get("completedQuantity", 0))),
            "dueDate": data.get("dueDate") or (datetime.now(timezone.utc).isoformat()),
            "assignedMachineId": data.get("assignedMachineId") or "CNC-02",
            "status": data.get("status", "IN_PROGRESS"),
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }
        self.store.put_order(order)
        if order.get("assignedMachineId"):
            try:
                self.store.update_machine(order["assignedMachineId"], {"status": "RUNNING", "currentOrderId": order["id"]})
            except Exception:
                pass
        self.store.add_audit({
            "id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": now_iso(),
            "actor": data.get("createdBy", "SUPERVISOR-DIR-01"),
            "event": "ORDER_CREATED",
            "orderId": order["id"],
        })
        risk = self.calculate_risk(order["id"])
        order["risk"] = risk
        return order

    def create_machine(self, data: dict[str, Any]) -> dict[str, Any]:
        machine_id = (data.get("id") or f"MC-{uuid.uuid4().hex[:4].upper()}").strip().upper()
        caps = data.get("capabilities", ["MACHINING"])
        if isinstance(caps, str):
            caps = [c.strip().upper() for c in caps.split(",") if c.strip()]
        machine = {
            "id": machine_id,
            "name": data.get("name") or machine_id,
            "type": data.get("type", "CNC Workstation"),
            "status": data.get("status", "AVAILABLE"),
            "capacityPerHour": max(5, int(data.get("capacityPerHour", 25))),
            "capabilities": caps or ["MACHINING"],
            "lastEventAt": now_iso(),
        }
        self.store.put_machine(machine)
        self.store.add_audit({
            "id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": now_iso(),
            "actor": data.get("createdBy", "FACILITY-ENG-01"),
            "event": "MACHINE_REGISTERED",
            "orderId": machine_id,
        })
        return machine

    def ingest_event(self, event: dict[str, Any], publish: bool = True) -> dict[str, Any]:
        event = dict(event)
        event.setdefault("id", f"EVT-{uuid.uuid4().hex[:10].upper()}")
        event.setdefault("timestamp", now_iso())
        event.setdefault("source", "manual")
        event.setdefault("plantId", "PLANT-001")
        event.setdefault("type", "GENERAL")
        self.store.add_event(event)
        if self.s3_client and self.raw_bucket:
            key = f"events/{event['timestamp'][:10]}/{event['id']}.json"
            self.s3_client.put_object(Bucket=self.raw_bucket, Key=key, Body=json.dumps(event).encode(), ContentType="application/json")
        if publish and self.events_client:
            self.events_client.put_events(Entries=[{
                "EventBusName": self.event_bus,
                "Source": "opsrelay.ingestion",
                "DetailType": "FactoryEvent",
                "Detail": json.dumps(event),
            }])
        elif publish:
            self.process_event(event)
        return event

    def process_event(self, event: dict[str, Any]) -> dict[str, Any]:
        order_id = event.get("orderId")
        if not order_id:
            return {"processed": True, "risk": None}
        et = event.get("type")
        machine_id = event.get("machineId")
        if machine_id and et in {"MACHINE_STOP", "MACHINE_DEGRADED", "MACHINE_RECOVERED"}:
            status = {"MACHINE_STOP": "STOPPED", "MACHINE_DEGRADED": "DEGRADED", "MACHINE_RECOVERED": "AVAILABLE"}[et]
            try: self.store.update_machine(machine_id, {"status": status, "lastEventAt": event["timestamp"]})
            except KeyError: pass
        risk = self.calculate_risk(order_id)
        return {"processed": True, "risk": risk}

    def _generate_recommendation(self, order: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any] | None:
        if risk["riskScore"] < 35: return None
        existing = [r for r in self.store.list_recommendations(order["id"]) if r.get("status") == "OPEN"]
        if existing: return existing[-1]
        options = self.available_machines(order["id"])
        if options:
            action_type = "REASSIGN_MACHINE"
            target = options[0]["id"]
            rationale = f"Reassign remaining {order['product']} work from {order.get('assignedMachineId')} to {target} to restore available capacity."
        else:
            action_type = "ESCALATE_MAINTENANCE"
            target = order.get("assignedMachineId")
            rationale = f"Escalate {target} for maintenance because no compatible spare machine is currently available."
        rec = {
            "id": f"REC-{uuid.uuid4().hex[:8].upper()}",
            "orderId": order["id"],
            "actionType": action_type,
            "target": target,
            "rationale": rationale,
            "riskScore": risk["riskScore"],
            "confidence": round(min(0.99, 0.65 + risk["riskScore"]/300), 2),
            "status": "OPEN",
            "createdAt": now_iso(),
        }
        self.store.put_recommendation(rec)
        if order.get("status") in {"AT_RISK", "DELAYED", "INVESTIGATING"}:
            self.store.update_order(order["id"], {"status": "RECOVERY_PENDING"})
            order["status"] = "RECOVERY_PENDING"
        return rec

    def create_action(self, recommendation_id: str, approved_by: str = "SUP-001") -> dict[str, Any]:
        recs = self.store.list_recommendations()
        rec = next((r for r in recs if r["id"] == recommendation_id), None)
        if not rec: raise KeyError(recommendation_id)
        if rec.get("status") != "OPEN": raise ValueError("Recommendation is not open")
        order = self.store.get_order(rec["orderId"])
        if not order: raise KeyError(rec["orderId"])
        action = {
            "id": f"ACT-{uuid.uuid4().hex[:8].upper()}",
            "orderId": order["id"],
            "recommendationId": recommendation_id,
            "type": rec["actionType"],
            "target": rec.get("target"),
            "status": "APPROVED",
            "approvedBy": approved_by,
            "approvedAt": now_iso(),
        }
        self.store.put_action(action)
        self.store.update_order(order["id"], {"status": "RECOVERY_EXECUTING"})
        self._execute_action(action, rec)
        self.store.add_audit({"id": f"AUD-{uuid.uuid4().hex[:8].upper()}", "timestamp": now_iso(), "actor": approved_by, "event": "ACTION_APPROVED_AND_EXECUTED", "actionId": action["id"], "orderId": order["id"]})
        rec["status"] = "EXECUTED"
        self.store.put_recommendation(rec)
        return next((x for x in self.store.list_actions(order["id"]) if x["id"] == action["id"]), action)

    def _execute_action(self, action: dict[str, Any], rec: dict[str, Any]) -> None:
        order = self.store.get_order(action["orderId"])
        if rec["actionType"] == "REASSIGN_MACHINE" and rec.get("target"):
            old = order.get("assignedMachineId")
            self.store.update_order(order["id"], {"assignedMachineId": rec["target"], "status": "RECOVERY_VERIFIED"})
            if old: 
                try: self.store.update_machine(old, {"status": "AVAILABLE", "currentOrderId": None})
                except KeyError: pass
            try: self.store.update_machine(rec["target"], {"status": "RUNNING", "currentOrderId": order["id"]})
            except KeyError: pass
            action["status"] = "COMPLETED"
            action["executedAt"] = now_iso()
        else:
            self.store.update_order(order["id"], {"status": "MAINTENANCE_ESCALATED"})
            action["status"] = "COMPLETED"
            action["executedAt"] = now_iso()
        self.store.put_action(action)
        self.calculate_risk(order["id"])

    def reschedule_order(self, order_id: str, new_due_date: str, new_quantity: int | None = None, actor: str = "SUPERVISOR-DIR-01") -> dict[str, Any]:
        """Diagram 03: Reschedule Order use case."""
        order = self.store.get_order(order_id)
        if not order: raise KeyError(order_id)
        patch = {"dueDate": new_due_date}
        if new_quantity is not None:
            patch["quantity"] = max(1, int(new_quantity))
        self.store.update_order(order_id, patch)
        self.store.add_audit({
            "id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": now_iso(),
            "actor": actor,
            "event": "ORDER_RESCHEDULED",
            "orderId": order_id,
        })
        risk = self.calculate_risk(order_id)
        updated = self.store.get_order(order_id)
        updated["risk"] = risk
        return updated

    def transition_machine(self, machine_id: str, action: str, actor: str = "MAINTENANCE-LEAD") -> dict[str, Any]:
        """Diagram 08: UML State Machine (Machine) transitions."""
        machines = self.store.list_machines()
        m = next((x for x in machines if x["id"] == machine_id), None)
        if not m: raise KeyError(machine_id)
        action_upper = action.upper()
        status_map = {
            "DIAGNOSE": "DIAGNOSING",
            "REPAIR": "MAINTENANCE",
            "PLAN_MAINTENANCE": "MAINTENANCE",
            "FIX": "AVAILABLE",
            "COMPLETE_MAINTENANCE": "AVAILABLE",
            "RECOVER": "AVAILABLE",
            "STOP": "STOPPED",
            "DEGRADE": "DEGRADED",
            "START": "RUNNING",
        }
        next_status = status_map.get(action_upper)
        if not next_status:
            raise ValueError(f"Unknown machine transition action: {action}")

        patch = {"status": next_status, "lastEventAt": now_iso()}
        if next_status in {"AVAILABLE", "MAINTENANCE", "STOPPED", "DIAGNOSING"}:
            patch["currentOrderId"] = None
        updated = self.store.update_machine(machine_id, patch)
        self.store.add_audit({
            "id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": now_iso(),
            "actor": actor,
            "event": "MACHINE_TRANSITION",
            "action": action_upper,
            "orderId": machine_id,
            "details": f"Machine transitioned to {next_status} via {action_upper}",
        })
        for o in self.store.list_orders():
            if o.get("assignedMachineId") == machine_id:
                self.calculate_risk(o["id"])
        return updated

    def ask_agent(self, question: str, order_id: str | None = None) -> dict[str, Any]:
        # Diagram 07: When investigating an order, transition status to INVESTIGATING
        if order_id:
            try:
                order = self.store.get_order(order_id)
                if order and order.get("status") == "AT_RISK":
                    self.store.update_order(order_id, {"status": "INVESTIGATING"})
            except Exception:
                pass
        return self.agent.ask(question, order_id)
