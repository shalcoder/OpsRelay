import tempfile
from pathlib import Path

from core.risk import assess_order
from core.store import JsonStore
from core.service import OpsRelayService


def test_risk_detects_stopped_machine():
    order={"id":"ORD-1","quantity":100,"completedQuantity":10,"dueDate":"2099-01-01T00:00:00+00:00","assignedMachineId":"M1","product":"Valve","process":"MACHINING"}
    machines=[{"id":"M1","status":"STOPPED","capabilities":["MACHINING"]},{"id":"M2","status":"AVAILABLE","capabilities":["MACHINING"]}]
    events=[{"id":"E1","orderId":"ORD-1","type":"MACHINE_STOP","machineId":"M1","durationMinutes":80,"timestamp":"2026-09-20T10:00:00+00:00"}]
    risk=assess_order(order,machines,events,{"delayProbability":0.8,"failureProbability":0.7,"anomalyScore":0.5})
    assert risk["riskScore"] >= 60
    assert risk["severity"] in {"HIGH","CRITICAL"}


def test_service_local_event_generates_recommendation():
    with tempfile.TemporaryDirectory() as td:
        path=str(Path(td)/"db.json")
        store=JsonStore(path)
        store.put_order({"id":"ORD-1","quantity":100,"completedQuantity":20,"dueDate":"2099-01-01T00:00:00+00:00","assignedMachineId":"M1","product":"Valve","process":"MACHINING","status":"IN_PROGRESS"})
        store.put_machine({"id":"M1","status":"STOPPED","capabilities":["MACHINING"]})
        store.put_machine({"id":"M2","status":"AVAILABLE","capabilities":["MACHINING"]})
        svc=OpsRelayService(store)
        svc.ingest_event({"orderId":"ORD-1","machineId":"M1","type":"MACHINE_STOP","durationMinutes":90}, publish=False)
        svc.process_event(store.list_events("ORD-1")[0])
        risk=svc.get_risk("ORD-1")
        recs=store.list_recommendations("ORD-1")
        assert risk["riskScore"] >= 60
        assert recs
        assert recs[0]["actionType"] == "REASSIGN_MACHINE"
