from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _hours_until(due_iso: str, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    due = datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return (due - now).total_seconds() / 3600.0


def assess_order(order: dict[str, Any], machines: list[dict[str, Any]], events: list[dict[str, Any]], prediction: dict[str, float] | None = None) -> dict[str, Any]:
    qty = max(1, int(order.get("quantity", 1)))
    done = int(order.get("completedQuantity", 0))
    progress = _clamp((done / qty) * 100)
    remaining_ratio = 1 - progress / 100

    due_hours = _hours_until(order["dueDate"])
    due_pressure = 0 if due_hours >= 48 else 15 if due_hours >= 24 else 30 if due_hours >= 8 else 45 if due_hours >= 0 else 65

    order_id = order["id"]
    order_events = [e for e in events if e.get("orderId") == order_id]
    recent = sorted(order_events, key=lambda x: x.get("timestamp", ""), reverse=True)[:50]

    downtime_minutes = sum(float(e.get("durationMinutes", 0)) for e in recent if e.get("type") in {"MACHINE_STOP", "MACHINE_DEGRADED"})
    rework_units = sum(int(e.get("reworkUnits", 0)) for e in recent if e.get("type") == "QUALITY_REWORK")
    material_delay = max([float(e.get("delayHours", 0)) for e in recent if e.get("type") == "MATERIAL_DELAY"] or [0])
    downtime_factor = _clamp(downtime_minutes / 180 * 25)
    rework_factor = _clamp(rework_units / max(1, qty) * 100 * 0.2)
    material_factor = _clamp(material_delay / 12 * 20)

    assigned = order.get("assignedMachineId")
    machine = next((m for m in machines if m.get("id") == assigned), None)
    machine_factor = 0
    if machine:
        if machine.get("status") == "STOPPED":
            machine_factor = 25
        elif machine.get("status") == "DEGRADED":
            machine_factor = 12

    active_machines = sum(1 for m in machines if m.get("status") in {"AVAILABLE", "RUNNING"})
    contention_factor = 8 if active_machines <= 1 and remaining_ratio > 0.3 else 3 if active_machines <= 2 else 0

    ml_delay = float((prediction or {}).get("delayProbability", 0)) * 35
    ml_failure = float((prediction or {}).get("failureProbability", 0)) * 15
    ml_anomaly = float((prediction or {}).get("anomalyScore", 0)) * 10

    score = _clamp(
        due_pressure * 0.35
        + downtime_factor * 0.75
        + rework_factor
        + material_factor
        + machine_factor
        + contention_factor
        + ml_delay
        + ml_failure
        + ml_anomaly
        + (15 if progress < 25 and due_hours < 24 else 0)
    )

    severity = "CRITICAL" if score >= 80 else "HIGH" if score >= 60 else "WATCH" if score >= 35 else "HEALTHY"
    factors = []
    if machine_factor:
        factors.append(f"Assigned machine is {machine.get('status', '').lower()}")
    if downtime_minutes:
        factors.append(f"{round(downtime_minutes)} minutes of recent downtime/degradation")
    if rework_units:
        factors.append(f"{rework_units} units routed to rework")
    if material_delay:
        factors.append(f"Material delay of {round(material_delay, 1)} hours")
    if due_hours < 24:
        factors.append(f"Only {round(max(due_hours, 0), 1)} hours remain to due time")
    if prediction:
        factors.append(f"ML predicts {round(float(prediction.get('delayProbability', 0))*100)}% delay probability")
    if not factors:
        factors.append("No material operational risk signal detected")

    return {
        "orderId": order_id,
        "riskScore": round(score, 1),
        "severity": severity,
        "dueHours": round(due_hours, 2),
        "progressPercent": round(progress, 1),
        "factors": factors,
        "prediction": prediction or {"delayProbability": 0.0, "failureProbability": 0.0, "anomalyScore": 0.0},
        "calculatedAt": datetime.now(timezone.utc).isoformat(),
    }
