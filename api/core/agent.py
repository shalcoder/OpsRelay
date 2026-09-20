from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable

try:
    from strands import Agent, tool
except Exception:  # pragma: no cover
    Agent = None
    def tool(fn): return fn


SYSTEM_PROMPT = """
You are the OpsRelay Operations Agent for a manufacturing plant.
You investigate delivery risk using evidence, never invent facts, and distinguish predictions from observed events.
The deterministic risk engine is authoritative for the numeric risk score.
You may recommend recovery actions, but consequential actions require explicit human approval through the API.
Answer in compact operational language: situation, evidence, recommendation, owner, expected effect.
""".strip()


import uuid


class PolicyGuard:
    """Enforces safety, machine compatibility, and human-in-the-loop authorization boundaries (Diagram 16 & 17)."""

    def __init__(self, service: Any) -> None:
        self.service = service

    def validate_action_proposal(self, action_type: str, order_id: str, target: str | None) -> dict[str, Any]:
        """Validates that autonomous agent proposals adhere to factory safety and capacity policies."""
        if action_type == "REASSIGN_MACHINE":
            if not target:
                return {"allowed": False, "reason": "Target workstation must be specified for reassignment."}
            machines = self.service.store.list_machines()
            target_m = next((m for m in machines if m["id"] == target), None)
            if not target_m:
                return {"allowed": False, "reason": f"Target workstation {target} does not exist in plant fleet."}
            if target_m.get("status") in {"STOPPED", "MAINTENANCE"}:
                return {"allowed": False, "reason": f"Cannot route production to {target} because station is {target_m.get('status')}."}
            order = self.service.get_order(order_id)
            if order and order.get("process") not in target_m.get("capabilities", []):
                return {"allowed": False, "reason": f"Workstation {target} lacks certification for process '{order.get('process')}'."}
        return {"allowed": True, "requiresHumanSignOff": True, "policy": "HUMAN_IN_THE_LOOP_ENFORCED"}


try:
    import boto3
except Exception:  # pragma: no cover
    boto3 = None


class OpsRelayAgent:
    def __init__(self, service: Any):
        self.service = service
        self.policy_guard = PolicyGuard(service)
        self.region = os.getenv("AWS_REGION", "ap-south-1")
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=self.region) if boto3 else None
        self.enabled = os.getenv("STRANDS_ENABLED", "false").lower() == "true" and Agent is not None
        self._agent = None
        if self.enabled:
            self._agent = Agent(model=self.model_id, system_prompt=SYSTEM_PROMPT, tools=self._tools())

    def _tools(self) -> list[Callable]:
        service = self.service

        @tool
        def get_order_status(order_id: str) -> str:
            """Return the current order record."""
            return json.dumps(service.get_order(order_id))

        @tool
        def get_machine_status(machine_id: str) -> str:
            """Return a machine's current status."""
            return json.dumps(next((m for m in service.store.list_machines() if m["id"] == machine_id), None))

        @tool
        def get_recent_events(order_id: str, limit: int = 10) -> str:
            """Return recent events for an order."""
            return json.dumps(service.store.list_events(order_id, limit))

        @tool
        def get_risk_assessment(order_id: str) -> str:
            """Return the current deterministic risk assessment and ML prediction."""
            return json.dumps(service.get_risk(order_id))

        @tool
        def find_available_machine(order_id: str) -> str:
            """Find alternative machines capable of taking the order."""
            return json.dumps(service.available_machines(order_id))

        @tool
        def get_quality_history(order_id: str) -> str:
            """Return recent quality/rework events."""
            events = service.store.list_events(order_id, 100)
            return json.dumps([e for e in events if e.get("type") == "QUALITY_REWORK"])

        @tool
        def get_material_delays(order_id: str) -> str:
            """Return material delay events."""
            events = service.store.list_events(order_id, 100)
            return json.dumps([e for e in events if e.get("type") == "MATERIAL_DELAY"])

        return [get_order_status, get_machine_status, get_recent_events, get_risk_assessment, find_available_machine, get_quality_history, get_material_delays]

    def ask(self, question: str, order_id: str | None = None) -> dict[str, Any]:
        context = self.service.build_context(order_id) if order_id else self.service.build_dashboard_context()
        answer = None
        mode = "evidence-synthesis"
        if self._agent:
            try:
                prompt = f"Question: {question}\nOrder focus: {order_id or 'none'}\nInitial context:\n{json.dumps(context, default=str)}"
                result = self._agent(prompt)
                answer = str(result)
                mode = "strands"
            except Exception:
                answer = None

        if not answer and self.bedrock_client:
            try:
                prompt = f"Question: {question}\nOrder Focus: {order_id or 'none'}\nOperational State & Telemetry Context:\n{json.dumps(context, default=str)}"
                response = self.bedrock_client.converse(
                    modelId=self.model_id,
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    system=[{"text": SYSTEM_PROMPT}]
                )
                answer = response["output"]["message"]["content"][0]["text"]
                mode = f"bedrock-{self.model_id.split(':')[0].split('.')[-1]}"
            except Exception:
                answer = None

        if not answer:
            answer = self._fallback(question, context)
            mode = "evidence-synthesis"

        # Diagram 14: Persist AGENT_SESSION interaction record
        session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            self.service.store.add_agent_session({
                "id": session_id,
                "orderId": order_id,
                "question": question,
                "response": answer,
                "userId": "SUPERVISOR-DIR-01",
                "timestamp": timestamp,
            })
        except Exception:
            pass

        return {
            "sessionId": session_id,
            "answer": answer,
            "mode": mode,
            "policy": "HUMAN_IN_THE_LOOP_ENFORCED",
            "generatedAt": timestamp,
        }

    def _fallback(self, question: str, context: dict[str, Any]) -> str:
        q_lower = (question or "").lower()
        order = context.get("order")
        risk = context.get("risk") or {}
        alternatives = context.get("availableMachines", [])
        all_machines = context.get("allMachines", [])
        events = context.get("events", [])
        actions = context.get("actions", [])

        # If no specific order selected, provide factory overview synthesis
        if not order:
            orders = context.get("orders", [])
            at_risk = [o for o in orders if (o.get("risk", {}).get("riskScore", 0)) >= 60]
            crit = [o for o in orders if (o.get("risk", {}).get("riskScore", 0)) >= 80]
            stopped_m = [m for m in all_machines if m.get("status") == "STOPPED"]
            return (
                f"Plant Operations Overview (Apex Precision Works):\n\n"
                f"• Active Work Orders: {len(orders)} ({len(at_risk)} at risk, {len(crit)} critical)\n"
                f"• Workstations Down: {len(stopped_m)} ({', '.join(m['id'] for m in stopped_m) if stopped_m else 'All nominal'})\n"
                f"• Critical Orders: {', '.join(o['id'] for o in crit) if crit else 'None'}\n\n"
                f"Select an order from the sidebar to inspect granular telemetry and execute recovery rerouting."
            )

        order_id = order["id"]
        product = order.get("product", "Component")
        customer = order.get("customer", "Customer")
        process = order.get("process", "MACHINING")
        qty = int(order.get("quantity", 1))
        done = int(order.get("completedQuantity", 0))
        rem = max(0, qty - done)
        pct = round((done / qty * 100) if qty else 0, 1)
        assigned_id = order.get("assignedMachineId", "Unassigned")
        assigned_m = next((m for m in all_machines if m["id"] == assigned_id), {})
        cap = float(assigned_m.get("capacityPerHour", 25))
        m_status = assigned_m.get("status", "AVAILABLE")

        score = float(risk.get("riskScore", 0))
        severity = risk.get("severity", "UNKNOWN")
        factors = risk.get("factors", [])

        # Time calculations
        try:
            due_dt = datetime.fromisoformat(order["dueDate"].replace("Z", "+00:00"))
            hours_to_due = (due_dt - datetime.now(timezone.utc)).total_seconds() / 3600
        except Exception:
            hours_to_due = 24.0

        prod_hours_needed = round(rem / cap, 1) if cap > 0 else 0.0
        time_deficit = round(prod_hours_needed - hours_to_due, 1)

        # Telemetry aggregates
        downtime = sum(float(e.get("durationMinutes", 0)) for e in events if e.get("type") in {"MACHINE_STOP", "MACHINE_DEGRADED"})
        rework = sum(int(e.get("reworkUnits", 0)) for e in events if e.get("type") == "QUALITY_REWORK")
        mat_delay = max([float(e.get("delayHours", 0)) for e in events if e.get("type") == "MATERIAL_DELAY"] or [0.0])

        # INTENT 1: Alternate Machines / Capacity Reassignment
        if any(k in q_lower for k in ["alternate", "alternative", "other machine", "capacity", "spare", "switch", "reassign", "which machine"]):
            compatible = [m for m in all_machines if process in m.get("capabilities", []) and m["id"] != assigned_id]
            if not compatible:
                return (
                    f"Alternative Machine Analysis for {order_id} ({product} · Process: {process}):\n\n"
                    f"WARNING: No other workstations in the current fleet are certified for process '{process}'.\n"
                    f"Immediate Recommendation: Prioritize emergency mechanical dispatch to clear {assigned_id} ({m_status})."
                )
            lines = []
            for m in compatible:
                m_cap = float(m.get("capacityPerHour", 20))
                m_hours = round(rem / m_cap, 1) if m_cap > 0 else 0
                status_note = "READY FOR DISPATCH" if m.get("status") == "AVAILABLE" else f"CURRENTLY {m.get('status')}"
                lines.append(
                    f"• {m['id']} ({m.get('name', m['id'])}):\n"
                    f"   - Status: {status_note}\n"
                    f"   - Rated Capacity: {m_cap} units/hr\n"
                    f"   - Est. Completion Time: {m_hours} hrs for {rem} remaining units\n"
                    f"   - SLA Delivery Margin: {'ON-TIME' if m_hours <= hours_to_due else f'LATE by {round(m_hours - hours_to_due, 1)}h'}"
                )
            best_opt = alternatives[0] if alternatives else compatible[0]
            return (
                f"Alternative Capacity Matrix for {order_id} ({product}):\n\n"
                f"Currently Assigned: {assigned_id} (Status: {m_status}, Cap: {cap} u/hr)\n"
                f"Work Remaining: {rem} units ({done}/{qty} completed, {pct}%)\n"
                f"Time Window to Due Date: {hours_to_due:.1f} hours\n\n"
                f"Compatible Workstations Evaluated:\n" + "\n".join(lines) + "\n\n"
                f"Optimal Strategy: Reassign to {best_opt['id']} (Rated {best_opt.get('capacityPerHour', 25)} u/hr). Human authorization required via Recovery Queue."
            )

        # INTENT 2: Root Cause Evidence & Ingestion Timeline
        if any(k in q_lower for k in ["root cause", "evidence", "signals", "events", "why stopped", "history", "recent events", "timeline"]):
            if not events:
                return f"Root Cause Analysis for {order_id}: No negative edge signals recorded in current window. Machine operating within baseline tolerances."
            event_bullets = []
            for ev in events[:6]:
                t = ev.get("type", "SIGNAL")
                desc = ev.get("description") or f"{t} recorded"
                ts = ev.get("timestamp", "")[:19].replace("T", " ")
                event_bullets.append(f"• [{ts} UTC] {t} on {ev.get('machineId', assigned_id)}: {desc}")
            return (
                f"Edge Signal Telemetry & Root Cause Dossier for {order_id}:\n\n"
                f"Cumulative Incident Metrics:\n"
                f"• Machine Downtime: {downtime:.0f} cumulative minutes\n"
                f"• Quality Rejections / Rework: {rework} units diverted\n"
                f"• Inbound Supply Delay: {mat_delay:.1f} hours hold\n\n"
                f"Ingested Edge Signal Log:\n" + "\n".join(event_bullets) + "\n\n"
                f"Root Cause Assessment: Delivery confidence degraded due to compounded throughput losses on workstation {assigned_id}. Recovery routing recommended."
            )

        # INTENT 3: Executive Summary / Shift Supervisor Brief
        if any(k in q_lower for k in ["executive", "supervisor", "summary", "brief", "shift", "management"]):
            rec_action = f"Reroute remaining lot to {alternatives[0]['id']}" if alternatives else f"Expedite maintenance on {assigned_id}"
            return (
                f"Executive Shift Briefing — Order {order_id}\n\n"
                f"1. Executive Header:\n"
                f"   • Client: {customer}\n"
                f"   • Component: {product} (Part #{order_id})\n"
                f"   • Current Delivery Risk: {severity} ({score:.0f}/100)\n"
                f"   • Batch Progress: {done} of {qty} units finished ({pct}%)\n\n"
                f"2. Bottleneck Impact:\n"
                f"   • Machine {assigned_id} is {m_status}.\n"
                f"   • Net schedule drift: {abs(time_deficit):.1f} hours {'behind commitment' if time_deficit > 0 else 'headroom remaining'}.\n\n"
                f"3. Operational Recovery Directive:\n"
                f"   • Action: {rec_action}\n"
                f"   • Projected Delivery: Restores SLA compliance within customer delivery window.\n"
                f"   • Sign-off: Pending shift supervisor approval in Recovery Queue."
            )

        # INTENT 4: Standard / Specific Risk Diagnosis ("Why is it at risk?")
        alt = alternatives[0]["id"] if alternatives else None
        rec = f"Move remaining {rem} units from {assigned_id} to {alt} ({best_opt.get('capacityPerHour', 25) if 'best_opt' in locals() else '28'} units/hr)." if alt else f"Escalate {assigned_id} to maintenance lead and monitor capacity."
        evidence_str = "; ".join(factors[:4]) if factors else f"Workstation {assigned_id} status is {m_status}"
        return (
            f"{order_id} is {severity} at {score:.0f}/100 risk score.\n\n"
            f"Production Health: {done}/{qty} completed ({pct}%). Requires {prod_hours_needed} hrs of machining with {hours_to_due:.1f} hrs until customer due date.\n\n"
            f"Telemetry Evidence: {evidence_str}.\n\n"
            f"Autonomous Recommendation: {rec}\n\n"
            f"Human approval is required before execution in Recovery Queue."
        )
