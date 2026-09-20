import tempfile
from pathlib import Path
import pytest

from core.models import (
    Plant,
    User,
    ProductionOrder,
    Machine,
    FactoryEvent,
    RiskAssessment,
    Prediction,
    Evidence,
    Recommendation,
    Action,
    AgentSession,
)
from core.store import JsonStore
from core.service import OpsRelayService
from core.agent import OpsRelayAgent, PolicyGuard


def test_domain_dataclasses():
    """Diagram 04 & 14: Verify domain entities instantiate and serialize cleanly."""
    plant = Plant(id="PLANT-DETROIT", name="Detroit Advanced Propulsion Plant", location="Detroit, MI")
    assert plant.id == "PLANT-DETROIT"
    
    order = ProductionOrder(
        id="ORD-1048",
        customer="AeroTurbine Corp",
        product="Titanium Blisk",
        process="5-AXIS-MILLING",
        quantity=300,
        completedQuantity=80,
        dueDate="2026-09-22T18:00:00Z",
        assignedMachineId="CNC-07",
        status="IN_PROGRESS"
    )
    assert order.progress_percent == pytest.approx(26.66, 0.1)
    
    machine = Machine(
        id="CNC-07",
        name="DMG Mori 5-Axis #7",
        type="5-Axis CNC",
        capacityPerHour=20,
        status="AVAILABLE",
        capabilities=["5-AXIS-MILLING", "HIGH-SPEED-MILLING"]
    )
    assert machine.is_available() is True
    
    rec = Recommendation(
        id="REC-01",
        orderId="ORD-1048",
        actionType="REASSIGN_MACHINE",
        confidence=0.92,
        target="CNC-08",
        rationale="Reassign to idle mill",
        evidence=["Spindle overheated"]
    )
    d = rec.to_dict()
    assert d["confidence"] == 0.92
    assert d["target"] == "CNC-08"


def test_machine_state_machine_transitions():
    """Diagram 08: Machine State Machine Lifecycle."""
    with tempfile.TemporaryDirectory() as td:
        store = JsonStore(str(Path(td) / "store.json"))
        store.put_machine({"id": "CNC-07", "status": "AVAILABLE", "capabilities": ["MACHINING"]})
        svc = OpsRelayService(store)
        
        # AVAILABLE -> STOPPED
        res = svc.transition_machine("CNC-07", "STOP", actor="OPERATOR-01")
        assert res["status"] == "STOPPED"
        
        # STOPPED -> DIAGNOSING
        res = svc.transition_machine("CNC-07", "DIAGNOSE", actor="MAINT-01")
        assert res["status"] == "DIAGNOSING"
        
        # DIAGNOSING -> MAINTENANCE (REPAIR)
        res = svc.transition_machine("CNC-07", "REPAIR", actor="MAINT-01")
        assert res["status"] == "MAINTENANCE"
        
        # MAINTENANCE -> AVAILABLE (COMPLETE_MAINTENANCE)
        res = svc.transition_machine("CNC-07", "COMPLETE_MAINTENANCE", actor="MAINT-01")
        assert res["status"] == "AVAILABLE"
        
        # AVAILABLE -> MAINTENANCE (PLAN_MAINTENANCE)
        res = svc.transition_machine("CNC-07", "PLAN_MAINTENANCE", actor="SUPERVISOR-DIR-01")
        assert res["status"] == "MAINTENANCE"
        
        # Verify audit entries logged for transitions
        audits = store.list_audit()
        assert len(audits) >= 5
        assert any(a.get("event") == "MACHINE_TRANSITION" for a in audits)


def test_order_state_machine_and_reschedule():
    """Diagram 03 & 07: Production Order State Machine & Reschedule."""
    with tempfile.TemporaryDirectory() as td:
        store = JsonStore(str(Path(td) / "store.json"))
        store.put_order({
            "id": "ORD-1048",
            "quantity": 200,
            "completedQuantity": 20,
            "dueDate": "2026-09-21T00:00:00Z",
            "assignedMachineId": "CNC-07",
            "product": "Turbine Blade",
            "process": "MACHINING",
            "status": "IN_PROGRESS"
        })
        store.put_machine({"id": "CNC-07", "status": "STOPPED", "capabilities": ["MACHINING"]})
        store.put_machine({"id": "CNC-08", "status": "AVAILABLE", "capabilities": ["MACHINING"]})
        
        svc = OpsRelayService(store)
        
        # Ingest machine stop event -> moves to AT_RISK & generates RECOVERY_PROPOSED
        svc.ingest_event({"orderId": "ORD-1048", "machineId": "CNC-07", "type": "MACHINE_STOP", "durationMinutes": 120}, publish=False)
        event = store.list_events("ORD-1048")[0]
        svc.process_event(event)
        
        o = store.get_order("ORD-1048")
        assert o["status"] in {"AT_RISK", "RECOVERY_PROPOSED", "RECOVERY_PENDING"}
        
        # Execute Recommendation action -> moves to RECOVERY_VERIFIED
        recs = store.list_recommendations("ORD-1048")
        assert len(recs) > 0
        rec_id = recs[0]["id"]
        action = svc.create_action(rec_id, approved_by="SUPERVISOR-DIR-01")
        assert action["status"] in {"APPROVED", "COMPLETED"}
        
        o = store.get_order("ORD-1048")
        assert o["status"] in {"RECOVERY_EXECUTING", "RECOVERY_VERIFIED"}
        
        # Reschedule Order (Diagram 03 Use Case)
        rescheduled = svc.reschedule_order("ORD-1048", new_due_date="2099-01-01T00:00:00Z", new_quantity=180, actor="SUPERVISOR-DIR-01")
        assert rescheduled["dueDate"] == "2099-01-01T00:00:00Z"
        assert rescheduled["quantity"] == 180
        assert rescheduled["status"] == "IN_PROGRESS"
        assert rescheduled["risk"]["riskScore"] < 60


def test_policy_guard_and_agent_session():
    """Diagrams 14, 16 & 17: Agent Session Tracking & Policy Guard Safety Verification."""
    with tempfile.TemporaryDirectory() as td:
        store = JsonStore(str(Path(td) / "store.json"))
        store.put_order({
            "id": "ORD-1048",
            "quantity": 100,
            "completedQuantity": 10,
            "dueDate": "2099-01-01T00:00:00Z",
            "assignedMachineId": "CNC-07",
            "product": "Valve",
            "process": "MACHINING",
            "status": "IN_PROGRESS"
        })
        store.put_machine({"id": "CNC-07", "status": "AVAILABLE", "capabilities": ["MACHINING"]})
        store.put_machine({"id": "CNC-08", "status": "AVAILABLE", "capabilities": ["MACHINING"]})
        store.put_machine({"id": "WELD-01", "status": "AVAILABLE", "capabilities": ["WELDING"]})
        
        # Test Policy Guard
        svc = OpsRelayService(store)
        guard = PolicyGuard(svc)
        
        # CNC-08 has MACHINING capability and is AVAILABLE -> Allowed with human signoff
        res = guard.validate_action_proposal("REASSIGN_MACHINE", "ORD-1048", "CNC-08")
        assert res["allowed"] is True
        assert res["requiresHumanSignOff"] is True
        
        # WELD-01 lacks MACHINING capability -> Policy Guard rejects
        res = guard.validate_action_proposal("REASSIGN_MACHINE", "ORD-1048", "WELD-01")
        assert res["allowed"] is False
        assert "lacks certification" in res["reason"]
        
        # Unknown machine -> Policy Guard rejects
        res = guard.validate_action_proposal("REASSIGN_MACHINE", "ORD-1048", "NON-EXISTENT")
        assert res["allowed"] is False
        assert "does not exist" in res["reason"]
        
        # Query Agent and verify AgentSession recorded in store
        ans = svc.ask_agent("Why is ORD-1048 at risk?", order_id="ORD-1048")
        assert "answer" in ans
        
        sessions = store.list_agent_sessions("ORD-1048")
        assert len(sessions) >= 1
        assert sessions[0]["orderId"] == "ORD-1048"
        assert "ORD-1048" in sessions[0]["question"]
